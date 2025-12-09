import json
import pandas as pd

from dataclasses import dataclass
from math import pi, tan, radians
import re
import time
from functools import wraps

import os
JSON_DICT_NAME = "tool_types"
ROUTER_FAM = ["WR", "O-FLUTE", "WR COMP"]
MM_CUTOFF = 20.0 # Used to determine if dimensions are in mm if OAL value is greater than MM_CUTOFF

STATUS_CODE = {
    101: "JSON content is empty/missing.",
    102: "Excel content is empty/missing.",
    104: "Tool description not found in JSON data.",
    105: "Live Time data is empty/missing.",
    106: "JSON content is not a dictionary.",
    107: "'tool_types' key not found in JSON data.",
    108: "Missing key in JSON data.",

    200: "Conversion Error.",
    201: "Invalid data type conversion.",
    202: "Cannot convert multiple flute counts to int.",
    203: "Cannot convert single flute count to int.",
    204: "Description is missing.",
    205: "Full dimensions in complete description has to many or few values.",
    206: "Missing critical dimensions and/or description.",
    207: "Tool is a Corner Radius tool but corner radius dimension missing from description.",
    208: "Cannot convert to Millimeters when fractional dimensions are present.",
    209: "Neck present in description but no neck diameter/length found.",
    210: "Material missing diameter/OAL in 'MAT_DIMENSION' key.",
    211: "Tapered neck missing neck diameter in 'TAPERED_NECK_DIA' key.",

    301: "Tool could not assign a generic tool family (i.e. DRILL, EM)",
    302: "Bur cut type missing from description i.e. 'Doublecut', 'Singlecut' or 'Diamond cut'.",
    303: "Multiple flute counts not allowed for non 'Burs' tool types.",
    304: "Tool type not found in 'bur_type' column in reference excel.",
    305: "Diameter not found in diameter ranges in reference excel.",
    306: "Cannot calculate doublecut time with only single flute count.",
    307: "Cannot find flute count in description/'FluteCount' key.",
    308: "Cannot calculate flute length. Please enter flute length in 'LOC' key or add point angle to description.",

    401: "Tool calculations still in progress.",
    404: "Generic error placeholder.",
    #500: "Error accessing S3",
    500: "Error accessing Lambda Layer",

    900: "Success"
}
@dataclass
class ToolInfo:
    """
    Class to hold tool information
    """
    cut_diameter: float = 0.0
    length_of_cut: float = 0.0
    shank_diameter: float = 0.0
    overall_length: float = 0.0

    flute_length: float = 0.0
    tip_diameter: float = 0.0
    tip_length: float = 0.0
    pilot_length: float = 0.0
    corner_radius: float = 0.0
    neck_diameter: float = 0.0
    neck_length: float = 0.0
    tapered_neck_diameter: float = 0.0

    tapered_neck_angle: float = 0.0
    main_angle: float = 0.0

    material: str = ""
    material_diameter: float = 0.0
    material_oal: float = 0.0
    material_dimension = ""

    full_description: str = ""
    tool_description: str = ""
    bur_description: str = ""
    formatted_description: str = ""

    part_number: str = ""
    tool_family: str = ""
    reference_family: str = ""
    tool_type: str = ""
    flute_count: str = ""
    fluting_cycle_time: float = 0.0
    prep_cycle_time: float = 0.0
    prep_type: str = ""

@dataclass
class InputArgData:
    """
    Class to hold input argument and keyword arguments
    """
    tert_od_angle: bool = False
    notch: bool = False
    end_type: str = ""
    end_time: bool = False
    bur_cut: str = ""
    spiral: bool = False
    double_end: bool = False
    coarse: bool = False
    performance: bool = False
    detail: bool = False
    mass_detail: bool = False
    mm: bool = False
    prep: bool = False

class ContentDict:
    """
    Class to hold content information
    Args:
        status_code (int): The status code of the content.
        error_msg (str): The error message of the content.
        function (str): The function of the content.
        content (dict): Contains function results
    """
    def __init__(self, status_code: int, error_msg: str, function: str, content: dict):
        self.status_code = status_code
        self.error_msg = error_msg
        self.function = function
        self.content = content

    def __repr__(self):
        return f"ContentDict(status_code={self.status_code}, error={self.error_msg}, function={self.function}, content={self.content})"
    def __str__(self):
        return f"ContentDict(status_code={self.status_code}, error={self.error_msg}, function={self.function}, content={self.content})"
    
    def info(self):
        return {
            "status_code": self.status_code,
            "error": self.error_msg,
            "function": self.function,
            "content": self.content
        }
        
def lambda_handler(event, context):
    """
    This is a lambda function that will be called when an event is triggered containing
    the tool's diameter, length of cut, flute count, and description. *Metric units are accepted but everything must be in metric when calling this function.*
    
    Args:
        event (dict): A dictionary containing the following keys:
            event = {
                "Diameter": .5,
                "LOC": 1,
                "ShankDiameter": 1/2, 
                "OAL": 3-1/2,
                "FluteCount": "2/4",
                "Description": ".010x.015x1/8x2-1/2 3FL Square Mini-Mill with .0092x.035 Neck as Per Print, 6988 Rev C Tool# 10", # Accepts most of our current descriptions format
                "args": ["MM", "DETAIL"],
                "kwargs": {
                    "PART_NUM": "101-2666",
                    "MATERIAL": "SOLID", # Material type used to determine shank reduction prep for burs
                    "MAT_DIMENSION": "1/2x3" # Material diameter and oal
                    "TIP_DIAMETER": 0, # Accepts str or float but str must be "0" if using key
                    "TAPERED_NECK_DIA": 0
                    }
                }
                Diameter (str or float): # The diameter of the tool.
                LOC (str or float): # The length of cut of the tool.
                ShankDiameter (str or float): # The shank diameter of the tool.
                OAL (str or float): # The overall length of the tool.
                FluteCount (str): # The flute count which can be a single number(int) or a string indicating multiple counts (e.g., "2/4").
                Description (str): # If flute count is in description; it will take precedent over 'Flute Count' key or any other dimensions.
                args (list): # Optional list of arguments to specify additional features like 'TERT', 'DE', 'NOTCH', 'DETAIL', 'MM'.
                kwargs (dict): # Optional dictionary of keyword arguments, e.g., 'part_num' for part number.
        context (object): Lambda context object.
    Returns:
        dict: A dictionary with a statusCode of 900 and a body containing the calculated
        cycle time as a string. *'CycleTime' will be formatted in minutes*
        Example of output dict:
        {
            "statusCode": 900,
            "errorMessage": "Success!",
            "PartNumber": "101-101",
            "Diameter": 0.25,
            "LOC": 0.375,
            "ShankDiameter": 0.25,
            "OAL": 2,
            "FluteCount": "8/5",
            "Description": "08500 1/4X3/8X1/4X2 OVAL DOUBLECUT WITH .113X.6395 NECK",
            "Family": "BUR",
            "PrepType": "Neck Prep (Before Fluting): 6.9652 | Robot Time: 0",
            "CycleTime": 2.489,
            "PrepTime": 6.965,
            "TotalCycleTime": 9.454,
            "Detail": "Tool Type: OVAL DC\nDiameter: 0.25\nLength of Cut: 0.375\nShank Diameter: 0.25\nOAL: 2.0\nFlute Count: 8/5\nCycle Time: 2.489\nIncrease Percentage: 0%\n\nPrep Cycle Time: 6.965\nPrep Type: Neck Prep (Before Fluting): 6.9652 | Robot Time: 0\n\n------Base Cycle Times------\nSingle Cut Time: 2.08\nDouble Cut Time: 0.41\n"
        }
    """
    start_time = time.time()
    DIA_STR = "Diameter"
    LOC_STR = "LOC"
    SHANKDIA_STR = "ShankDiameter"
    OAL_STR = "OAL"
    FLCNT_STR = "FluteCount"
    DESC_STR = "Description"
    part_num = ""
    
    # Check if key is in event
    if 'args' in event:
        args = event['args']
    else:
        args = []
    if 'kwargs' in event:
        kwargs = event['kwargs']
        for k, v in kwargs.items():
            if k.lower() == 'part_num':
                part_num = str(v)
            break
    else:
        kwargs = {}
    
    num_list = [DIA_STR, LOC_STR, SHANKDIA_STR, OAL_STR]
    string_list = [FLCNT_STR, DESC_STR]

    for key in event:
        if event[key] == "":
            if key in num_list:
                event[key] = 0
            elif key == string_list:
                event[key] = ""
    try:
        diameter = event[DIA_STR]
        loc = event[LOC_STR]
        shank_dia = event[SHANKDIA_STR]
        oal = event[OAL_STR]
        fl_cnt = event[FLCNT_STR]
        description = event[DESC_STR]
    except KeyError as e:
        code = 108
        if context is None:
            print(STATUS_CODE[code])
        return {
            'statusCode': code,
            'errorMessage': [STATUS_CODE[code]+ " " + str(e)] 
        }
    
    if description == "": # Description is required
        code = 204
        if context is None:
            print(STATUS_CODE[code])
        return {
            'statusCode': code,
            'errorMessage': [STATUS_CODE[code]]
        }
    tool = ToolInfo(
        cut_diameter=diameter, 
        length_of_cut=loc, 
        shank_diameter=shank_dia, 
        overall_length=oal, 
        flute_count=fl_cnt, 
        tool_description=description
    )
    #accepts multiple args and kwargs from event passed into calc_cycle_time
    vars_data = get_tool_detail(tool=tool, context=context, args=args, kwargs=kwargs)
    #vars_data = calc_cycle_time(tool=tool, context=context, args=args, kwargs=kwargs)

    if vars_data.status_code!= 900:
        code = vars_data.status_code
        msg = vars_data.error_msg
        
        if context is None:
            print(msg)    
        return {
            'statusCode': code,  
            'errorMessage': msg
        }
    else:
        tool, feature, detail = vars_data.content.values()
        if not isinstance(tool, ToolInfo):
            return {
                'statusCode': 404,
                'errorMessage': "tool variable is not a ToolInfo object"
            }
        code = vars_data.status_code
        data = {
            'PartNumber': part_num,
            'Diameter': tool.cut_diameter,
            'LOC': tool.length_of_cut,
            'ShankDiameter': tool.shank_diameter,
            'OAL': tool.overall_length,
            'FluteCount': tool.flute_count,
            'Description': tool.full_description,
            'Family': tool.tool_family,
            'PrepType': tool.prep_type,

            'CycleTime': tool.fluting_cycle_time,
            'PrepTime': tool.prep_cycle_time,
            'PrepType': tool.prep_type,
            
            'TotalCycleTime': round(tool.fluting_cycle_time + tool.prep_cycle_time,3),
            'Detail': detail,
        }
        if context is None:
            #print("\n\n", "=====================", "\n",data['Detail'], "\n", "=====================")
            return {
                'statusCode': code,  
                'errorMessage': "Success!",
                **data # Unpack data
            }
        end_time = time.time()
        print(f"Execution time: {end_time - start_time} seconds")
        return {
            'statusCode': code,  
            'errorMessage': "Success!",
            **data # Unpack data
        }

def memoize(func):
    """ 
    Memoize a function so that it caches its result based on input arguments (both args and kwargs).
    If the function is called again with the same arguments, it returns the cached result instead of calling the function again.
    """
    cache = dict()
    @wraps(func)
    def memoized_func(*args, **kwargs):
        # Create a cache key that includes both args and kwargs
        key = (args, tuple(sorted(kwargs.items())))
        if key not in cache:
            cache[key] = func(*args, **kwargs)
        return cache[key]
    return memoized_func

@memoize
def access_lambda_layer(context):
    """
    Access the Lambda layer containing the reference excel and json files.
    If the context is None, it is assumed that this is being run without Lambda context.
    Otherwise, the paths are determined by the Lambda environment.
    Status code 900 indicates success.
    Args:
        context (obj): The Lambda context.
    Returns:
        ContentDict (obj): A instance of the ContentDict class containing the status code, error message, and content.
    """
    json_content = {}
    excel_content = {}
    layer_content_dict = ContentDict(status_code=900, error_msg='', function='access_lambda_layer', content={'json': json_content, 'excel': excel_content})
    if context is None:
        
        cwd = os.getcwd()
        JSON_FILE = cwd + '/ref-layer/Tool Type.json'
        EXCEL_FILE = cwd + '/ref-layer/Data(With Live).xlsx'
    else:
        JSON_FILE = '/opt/Tool Type.json'
        EXCEL_FILE = '/opt/Data.xlsx'

    path_list = [JSON_FILE, EXCEL_FILE]
    try:
        for path in path_list:
            if path.endswith('.json'):
                with open(path, 'r') as f:
                    json_content = dict(json.load(f))
            elif path.endswith('.xlsx'):
                excel_content = pd.read_excel(path, sheet_name=None)
        
        if json_content == {}:
            code = 101
            layer_content_dict.status_code = code
            layer_content_dict.error_msg = STATUS_CODE[code] + " " + layer_content_dict.function
            return layer_content_dict
        if excel_content == {}:
            code = 102
            layer_content_dict.status_code = code
            layer_content_dict.error_msg = STATUS_CODE[code] + " " + layer_content_dict.function
            return layer_content_dict

        layer_content_dict.content['json'] = json_content
        layer_content_dict.content['excel'] = excel_content
        return layer_content_dict
    
    except Exception as e:
        code = 500
        layer_content_dict.status_code = code
        layer_content_dict.error_msg = STATUS_CODE[code] + "-- " + str(e)
        return layer_content_dict
@memoize
def get_json_from_layer(context):
    """
    Retrieves JSON data from either an S3 bucket or a Lambda layer and
    generates a list of all tool types by iterating through the JSON data.
    If the JSON data is empty or missing, it returns a status code of 101.
    
    Args:
        context (obj): The Lambda context.
    
    Returns:
        ContentDict (obj): A instance of the ContentDict class containing the status code, error message, and content.
    """
    json_content = {}
    layer_data = access_lambda_layer(context)
    
    if layer_data.status_code != 900:
        return layer_data
    data = layer_data.content
    json_content = dict(data['json'])

    tool_types_list = set()
    split_tool_type_list = set()
    temp_dict = {key: set() for key in ["EM", "O-FLUTE","WR","WR_COMP"]}

    json_content_dict = ContentDict(status_code=900, error_msg="", function="get_json_from_layer", content={'detail': {}})
    
    bur_cut_types = json_content[JSON_DICT_NAME]["bur_cut_types"]
    em_shapes = json_content[JSON_DICT_NAME]["em_shapes"]
    
    for key, items in json_content[JSON_DICT_NAME].items():
        for item in items:
            split_tool_type_list.update(item.split(" ")) # stores individual words needed to build description
            if key.islower(): # Ignore lowercase keys not added to tool_types_list
                continue
            if key == "EM" and item not in ["DRILLMILL", "STAGGERED TOOTH CHAMFERING"]:
                for shape in em_shapes:
                    combined = f"{shape} {item}"
                    tool_types_list.add(combined)
                    temp_dict[key].add(combined)
            elif key == "WR":
                tool_types_list.add(item)
                temp_dict[key].add(item)
                o_combined = (f"O-FLUTE {item}",f"OFX {item}") # Builds accepted tool types due to many different descriptions
                for x in o_combined:
                    tool_types_list.add(x)
                    temp_dict["O-FLUTE"].add(x)
                comp_combined = (f"MORT COMP {item}",f"COMP {item}")
                for x in comp_combined:
                    tool_types_list.add(x)
                    temp_dict["WR_COMP"].add(x)
            else:
                tool_types_list.add(item.upper())
    # Join existing tool types with new tool types
    for key in temp_dict:   
        json_content[JSON_DICT_NAME][key] = set(json_content[JSON_DICT_NAME][key]).union(set(temp_dict[key]))
    detail_dict = {
        "json_content": dict(json_content),
        "tool_types_list": list(sorted(tool_types_list)),
        "split_tool_type_list": list(sorted(split_tool_type_list)),
        "bur_cut_types": list(bur_cut_types)
    }

    json_content_dict.content['detail'] = detail_dict
    return json_content_dict
@memoize
def get_xlsx_from_layer(context):
    """
    Access the Lambda layer containing the reference excel file.

    Args:
        context (obj): The Lambda context.

    Returns:
        ContentDict (obj): A instance of the ContentDict class containing the status code, error message, and content.
    """
    excel_content = {}
    xlsx_content_dict = ContentDict(status_code=900, error_msg="", function="get_xlsx_from_layer", content={'excel': excel_content})
    #status_code, data = access_s3(context)
    layer_data = access_lambda_layer(context)
    if layer_data.status_code != 900:
        return layer_data
    excel_content = layer_data.content['excel']
    
    if not excel_content:
        code = 102
        xlsx_content_dict.status_code = code
        xlsx_content_dict.error_msg = STATUS_CODE[code] + " " + xlsx_content_dict.function
        return xlsx_content_dict

    xlsx_content_dict.content['excel'] = excel_content
    return xlsx_content_dict

#def parse_description(description: str, cut_dia: float = 0, loc: float = 0, shank_dia: float = 0, oal: float = 0, fl_cnt = None, context = None, using_mm = False, prep = False):
def parse_description(tool: ToolInfo, context = None, using_mm = False, prep = False):
    """
    Parses a tool description and returns a dictionary containing details about the tool such as base description, full dimensions, angle and flute count.

    Args:
        tool (obj): An instance of the ToolInfo class containing the tool description.
        context (obj): The Lambda context.
        using_mm (bool): A flag indicating whether the tool dimensions are in millimeters.
        prep (bool): A flag indicating whether the tool needs prep.

    Returns:
        ContentDict (obj): A instance of the ContentDict class containing the status code, error message, and content(details about the tool).
    """
    description = tool.tool_description.upper()
    pd_content_dict = ContentDict(
        status_code = 900, 
        error_msg = "", 
        function = "parse_description",
        content = {
            "json_content": {}, 
            "tool": tool}
        )
    tool.full_description = description
    split_tool_type_list = []
    formatted_description = ""
    base_description = ""
    fl_cnt_cs = False
    abbrev_dict = {}
    angle_list = []
    dimension_list = []
    coating = None
    layer_detail = get_json_from_layer(context) # Get JSON data
    if layer_detail.status_code != 900:
        pd_content_dict.status_code = layer_detail.status_code
        pd_content_dict.error_msg = layer_detail.error_msg

        return pd_content_dict
    
    layer_content = layer_detail.content['detail']

    json_content = layer_content["json_content"]
    tool_types_list = layer_content["tool_types_list"]
    split_tool_type_list = layer_content["split_tool_type_list"]
    bur_cut_types = layer_content["bur_cut_types"]
    
    abbrev_dict = json_content["abbreviations"]
    extras = json_content[JSON_DICT_NAME]["extras"]
    wr_cut = json_content[JSON_DICT_NAME]["wr_cut"]

    # ------------------------- Modifying description -------------------------

    remove_char_list = ["(", ")", ","] 
    for char in remove_char_list:
        description = description.replace(char, " ")

    description = " ".join(description.split())

    # Account for tools with included shapes that might be missing "INCLUDED"
    if any(cone in description for cone in ["RADIUS CONE", "POINTED CONE"]) and "INCLUDED" not in description:
        description = description.replace("RADIUS CONE", "INCLUDED RADIUS CONE").replace("POINTED CONE", "INCLUDED POINTED CONE")
    
    """# Replaces words in description with words in abbreviations dictionary
    count = 0
    unique_word = []
    while count < 2:
        for key, value in abbrev_dict.items():
            if key in description:
                description = description.replace(key, value)
        
        for word in description.split(" "):
            if word not in unique_word:
                unique_word.append(word)
        description = " ".join(unique_word)
        count += 1"""

    # Replace abbreviations in description (max 2 passes)
    for _ in range(2):
        for key, value in abbrev_dict.items():
            description = description.replace(key, value)
    # Remove duplicate words, preserve order
    words = description.split()
    seen = set()
    description = " ".join([w for w in words if not (w in seen or seen.add(w))])

    # Add Flute count to tools missing from description that are not burs
    missing_fl_desc = ["SPADE","SPOTTING","DRILL&COUNTERSINK"]
    found = [True if not "FL" in description else False for desc in missing_fl_desc if desc in description]
    if True in found:
        description = "2FL " + description
    tool.tool_description = description
    # ------------------------- Parsing description -------------------------

    split_description = description.split(" ")
    neck_pattern = r'(?:\.)?(?:\d+(?:\.\d+)?|\d+/\d+|\d+-\d+/\d+)?(?:°)?X(?:\.)?(?:\d+(?:\.\d+)?|\d+/\d+|\d+-\d+/\d+)? (?:TAPERED)?NECK' # Searches for neck dimensions in description
    neck_match = re.search(neck_pattern, description)
    neck_angle = 0
    if neck_match:
        if "°" in neck_match.group(0):
            dimensions = neck_match.group(0).replace(" TAPEREDNECK", "").replace("°", "") # tODO: Check if this works
            split_dim = [eval(dim.replace("-", "+")) for dim in dimensions.split("X")]
            neck_angle, tool.neck_length = split_dim
            neck_angle = int(neck_angle)*2 # Makes neck angle and included angle for later calculations
        else:
            dimensions = neck_match.group(0).replace(" NECK", "")
            split_dim = [eval(dim.replace("-", "+")) for dim in dimensions.split("X")]
            tool.neck_diameter, tool.neck_length = split_dim

        split_description = description.replace(neck_match.group(0), "").split(" ")
    else:
        if prep and "NECK" in description:
            code = 209
            pd_content_dict.status_code = code
            pd_content_dict.error_msg = STATUS_CODE[code]
            return pd_content_dict

    cr = tool.corner_radius
    if "CR" in split_description: # Search for corner radius dimension in description
        cr_pattern = r'(?:\d+)?(?:\.)?\d+(?:MM)? CR'
        cr_match = re.search(cr_pattern, description)
        if cr_match:
            cr_str = cr_match.group(0)
            if "MM" in cr_str:
                cr = float(cr_str.replace("MM CR", ""))
                using_mm = True
                if cr > 8: # Prevents error with descriptions regex where CR number is missing but full dimension are present before "CR"
                    cr_match = None
            else:
                cr = float(cr_str.replace(" CR", ""))
                if cr > 1:
                    cr_match = None
        else:
            if prep:
                code = 207
                pd_content_dict.status_code = code
                pd_content_dict.error_msg = STATUS_CODE[code] + " -- " + description
                return pd_content_dict
    tool.corner_radius = cr
    fl_cnt = tool.flute_count

    for word in split_description:
        
        fl_cnt_match = re.search(r'\d+FL', word) # Assign flute count if found in description
        if fl_cnt_match: 
            fl_cnt_cs = True # For countersink
            fl_cnt = fl_cnt_match.group(0).replace("FL", "")
            tool.flute_count = fl_cnt

        dim_match = re.search(r'\d+X\d+', word) or re.search(r'\d+X.\d+', word)
        if dim_match: # Find full dimensions in description i.e. 1/8x1/8x1-1/2
            dimension_list.append(word.lower())
        
        angle_match = re.search(r'\d+°', word)
        if angle_match:
            angle_list.append(angle_match[0].lower())
            
        if "POWER" in word:
            coating = word
        if "°" in word: # Prevents error with degree symbol
            word = word.replace("°", "")
        
        if word in split_tool_type_list or word in abbrev_dict.values():
            formatted_description += word + " "
            # Remove bur cut types from description, also removes "DE", "SPIRAL", etc. helps with formatting/sorting
            # Used to look in json file for basic form description
            if word not in bur_cut_types and word not in extras and word not in wr_cut:
                if word.isnumeric() == False:
                    base_description += word + " "
        else:
            continue    
    description = str(formatted_description.rstrip())

    cut_dia = tool.cut_diameter
    loc = tool.length_of_cut
    shank_dia = tool.shank_diameter
    oal = tool.overall_length

    if fl_cnt == "":
        code= 307
        pd_content_dict.status_code = code
        pd_content_dict.error_msg = STATUS_CODE[code]
        return pd_content_dict
    
    if dimension_list == []:
        full_dim = f"{cut_dia}x{loc}x{shank_dia}x{oal}"
        dimension_list.append(full_dim)

    if len(dimension_list) >= 1:
        full_dim = dimension_list[0]
        full_dim = full_dim.replace("-", "+")
        dims = full_dim.split("x")
        x_cnt = full_dim.count("x")
        try:
            oal = eval(dims[x_cnt]) # Last dimension is always OAL
            cut_dia = eval(dims[0])
            if x_cnt == 2:
                shank_dia = eval(dims[1])

            elif x_cnt == 3:
                loc = eval(dims[1])
                shank_dia = eval(dims[2])
            elif x_cnt == 4:
                loc = eval(dims[1])
                shank_dia = eval(dims[3])
            else:
                code = 205
                pd_content_dict.status_code = code
                pd_content_dict.error_msg = STATUS_CODE[code]
                return pd_content_dict
        except Exception as e:
            code = 206
            pd_content_dict.status_code = code
            pd_content_dict.error_msg = f"{STATUS_CODE[code]} {str(e)}"
            return pd_content_dict

    tool.cut_diameter = round(float(cut_dia), 4)
    tool.length_of_cut = float(loc)
    tool.shank_diameter = shank_dia
    tool.overall_length = oal
    
    main_angle = 0
    for angle in angle_list:
        try:
            index = split_description.index(angle)
            if index <= 2: # Flute count for non burs index in description
                main_angle = float(angle.replace("°", ""))
                break
        except:
            main_angle = float(angle.replace("°", "")) # For tapermill cases
            if "TAPERMILL" in description:
                main_angle *=2
            break
    
    if "/" not in full_dim:
        if oal > MM_CUTOFF and using_mm == False:
            using_mm = True
    elif "/" in full_dim and using_mm == True:
        code = 208
        pd_content_dict.status_code = code
        pd_content_dict.error_msg = STATUS_CODE[code]
        return pd_content_dict
    
    base_description = str(base_description.rstrip())

    if base_description not in tool_types_list:
        code = 104
        pd_content_dict.status_code = code
        pd_content_dict.error_msg = STATUS_CODE[code] + f" Parsed description: '{base_description}'"
        return pd_content_dict
    
    if "COUNTERSINK" in description: # Associate countersinks that are not burs to bur family due to similar calculations for cycle time
        if fl_cnt_cs != False and "DRILL" not in description:
            description += " ~ 90 INCLUDED CONE FM"
            tool.tool_description = description
            fl_cnt = int(fl_cnt)
        if main_angle:
            if "DRILL" in description: # For combo drill and countersink
                tool.pilot_length = (cut_dia + cut_dia/3.32856)-0.01
                multiplier = 4.0
                if shank_dia >= .5000:
                    multiplier = 3.2
                dia = shank_dia
            elif int(fl_cnt) == 1: # 1FL countersink
                multiplier = 2.3
                dia = cut_dia
            else:
                multiplier = 1.5 
                dia = cut_dia
            flute_length = find_height_tan(main_angle, dia)*multiplier
            tool.flute_length = flute_length
            if not loc: # No loc entered
                tool.length_of_cut = flute_length
        else:
            code = 308
            pd_content_dict.status_code = code
            pd_content_dict.error_msg = STATUS_CODE[code] + " -- " + tool.tool_description
            return pd_content_dict
        
    tool.formatted_description = base_description
    tool.bur_description = description
    #tool.tool_description = description
    def convert_from_mm(dimension): # Convert from mm to inches
        if dimension == 0:
            return 0
        return round(dimension / 25.4, 4)
    # Find non-zero float or int attributes in tool data class
    attribute_list = []
    for attr in tool.__dict__:
        if isinstance(getattr(tool, attr), (float, int)) and getattr(tool, attr) != 0:
            attribute_list.append(attr)
    if main_angle:
        tool.main_angle = main_angle
    if neck_angle:
        tool.tapered_neck_angle = neck_angle

    if attribute_list == []:
        code = 206
        pd_content_dict.status_code = code
        pd_content_dict.error_msg = STATUS_CODE[code] + " When full dimension is present in description."
        return pd_content_dict
    
    if using_mm == True:
        #dimension_dict = {key: convert_from_mm(value) for key, value in dimension_dict.items()}
        for attr in attribute_list:
            setattr(tool, attr, convert_from_mm(getattr(tool, attr)))
    
    pd_content_dict.content["tool"] = tool
    pd_content_dict.content['json_content'] = json_content
    return pd_content_dict

def chk_mirror_finish(inc_percentage, split_description): # Checks for tools with Mirror Finish
    if "MF" in split_description:
        inc_percentage += 0.2
    return inc_percentage
def find_height_tan(angle: float, dia: float):
    """
    Function calculates height/length of a tool based on angle given and diameter of tool.
    """
    if angle == 90.0:
        angle = 90.0/2.0
    else:
        angle = 90.0 - (angle/2.0) # /2 Accounts for included angles
    radius = dia / 2.0
    height = tan(radians(angle)) * radius
    return height

def get_family(json_content, base_description, split_description, context = None):

    """
    This function takes in the json_content dictionary, the base_description and split_description lists, and the Lambda context to determine the family of the tool. It checks the base_description against various lists of tool types and assigns the appropriate family, reference family, end type, bur cut, and spiral flag.

    Args:
        json_content (dict): The dictionary containing all the tool type information.
        base_description (list): The base description of the tool.
        split_description (list): The description of the tool split into a list.
        context (obj): The Lambda context.

    Returns:
        ContentDict (obj): A instance of the ContentDict class containing the status code, error message, and content.
    """
    EM_LIST = json_content[JSON_DICT_NAME]["EM"]
    BUR_LIST = json_content[JSON_DICT_NAME]["BUR"]
    DRILL_LIST = json_content[JSON_DICT_NAME]["DRILL"]
    FBGR_LIST = json_content[JSON_DICT_NAME]["FBGR"]
    WR_LIST = json_content[JSON_DICT_NAME]["WR"]
    O_FLUTE_LIST = json_content[JSON_DICT_NAME]["O-FLUTE"]
    WR_COMP_LIST = json_content[JSON_DICT_NAME]["WR_COMP"]
    BUR_CUT_LIST = json_content[JSON_DICT_NAME]["bur_cut_types"]

    family = ""
    ref_family = ""
    end_type = ""
    bur_cut = ""
    spiral = False
    
    fam_content_dict = ContentDict(
        status_code=900,
        error_msg="", 
        function="get_family",
        content={}
    )
    if base_description in EM_LIST:
        ref_family = "SQ EM"
        family = "EM"
    elif base_description in WR_LIST:
        ref_family = "SQ EM"
        family = "WR"
    elif base_description in DRILL_LIST:
        ref_family = "SQ EM"
        family = "DRILL"
    elif base_description in FBGR_LIST:
        end_type = split_description[0]
        ref_family = "BUR"
        family = "FBGR"
    elif base_description in O_FLUTE_LIST:
        ref_family = "SQ EM"
        family = "O-FLUTE"
    elif base_description in WR_COMP_LIST:
        ref_family = "SQ EM"
        family = "WR COMP"
    elif any(x in base_description for x in BUR_LIST) and "DRILL" not in base_description:
        for cut in BUR_CUT_LIST:
            if "SPIRAL" in split_description:
                spiral = True
            if cut in split_description:
                ref_family = "BUR"
                bur_cut = cut
                family = "BUR"
                break
        else:
            code = 302
            fam_content_dict.status_code = code
            fam_content_dict.error_msg = STATUS_CODE[code]
            return fam_content_dict
    else:
        code = 301
        fam_content_dict.status_code = code
        fam_content_dict.error_msg = STATUS_CODE[code]
        return fam_content_dict
    
    fam_info = {
        "family": family,
        "ref_family": ref_family,
        "end_type": end_type,
        "bur_cut": bur_cut,
        "spiral": spiral
    }
    fam_content_dict.content = fam_info
    return fam_content_dict

def calc_prep_time(tool: ToolInfo, context=None, parse: bool = True, double_end: bool = False):
    """
    Calculate the prep time for a given tool.

    Args:
        tool (ToolInfo): Object containing tool information.
        context (obj): Lambda context.
        parse (bool): Whether to parse the description of the tool.
        double_end (bool): Whether to double the prep time for double-end tools.

    Returns:
        ContentDict: Dictionary containing time, reduction_vol, and rate.
    """
    prep_content_dict = ContentDict(
        status_code=900, 
        error_msg="", 
        function="calc_prep_time", 
        content={"tool": tool})
    
    if parse == True:
        var_bundle = parse_description(tool, context, prep = True)
        if var_bundle.status_code != 900:
            return var_bundle
        json_content, tool = var_bundle.content.values()

        description = tool.tool_description
        
        family_info= get_family(json_content, description, description.split(" "))
        if family_info.status_code != 900:
            return family_info
        
        tool.tool_family = family_info.content["family"]

    dim_dict = tool.__dict__
    for key in dim_dict: # Converts all dimensions to floats
        if dim_dict[key] == 0.0:
            continue
        try:
            if isinstance(dim_dict[key], str):
                continue
            dim_dict[key] = float(dim_dict[key])
        except Exception as e:
            continue
    description = tool.tool_description
    cut_dia = tool.cut_diameter
    loc = tool.length_of_cut
    shank_dia = tool.shank_diameter
    oal = tool.overall_length
    cr = tool.corner_radius
    nk_dia = tool.neck_diameter
    nk_len = tool.neck_length
    mat = tool.material
    mat_dia = tool.material_diameter
    mat_len = tool.material_oal
    family = tool.tool_family
    
    split_description = description.split(" ")
    critical_dim = [cut_dia, loc, shank_dia]
    if any(x == 0.0 for x in critical_dim):
        code = 206
        prep_content_dict.status_code = code
        prep_content_dict.error_msg = STATUS_CODE[code] + " In prep calculation"
        return prep_content_dict
    
    json_layer = get_json_from_layer(context) # Get JSON data
    if json_layer.status_code != 900:
        json_layer.content = prep_content_dict.content
        return json_layer
    
    excel_layer = get_xlsx_from_layer(context) # Get Excel data
    if excel_layer.status_code != 900:
        return excel_layer
    
    json_content = json_layer.content['detail']["json_content"]
    DICT_NAME  = "prep" # JSON dictionary key
    PREP_DICT = json_content[DICT_NAME]

    if "DRILL&COUNTERSINK" in description:
        prep_length = tool.pilot_length
    else:
        prep_length = loc

    # Centerless grinding
    if mat_dia > cut_dia and mat_dia > shank_dia:
        cg_prep = True
    else:
        cg_prep = False
    
    if cut_dia < shank_dia: # Front reduction check
        front_reduction_prep = True
        FR_DICT = PREP_DICT["fr_prep"]

        
        if family == "DRILL":
            prep_dia = cut_dia
        # Generic prep diameter increase from nominal diameter
        elif cut_dia > FR_DICT["dia_cutoff1"]: # Tools larger than 0.2362
            prep_dia = cut_dia + FR_DICT["prep_dia_inc1"]
        else:
            if cut_dia >= FR_DICT["dia_cutoff2"]: # Tools larger than 0.030
                prep_dia = cut_dia + FR_DICT["prep_dia_inc2"]
            else:
                prep_dia = cut_dia + FR_DICT["prep_dia_inc3"]
    else:
        front_reduction_prep = False
        prep_dia = cut_dia
    
    if "BRAZED" in tool.material.upper():
        shank_dia = cut_dia

    if shank_dia < cut_dia: # Shank reduction
        shank_reduction_prep = True
    else:
        shank_reduction_prep = False

    nk_type = "BF" # Before Fluting
    
    if nk_dia: 
        neck_prep = True
        if nk_dia == cut_dia:# Neck prep check
            prep_length = loc + nk_len
            neck_prep = False
    else:
        neck_prep = False
    
    BT_DICT = PREP_DICT["backtaper_prep"]
    if any(word in description for word in BT_DICT["tools"]):
        backtaper_rate = BT_DICT["rate"]/25.4

        bt_time = prep_length/backtaper_rate
        backtaper_prep = True
    else:
        backtaper_prep = False
        bt_time = 0.0
        backtaper_rate = 0.0
    if "TAPEREDNECK" in description:
        if not tool.tapered_neck_diameter:
            code = 211
            prep_content_dict.status_code = code
            prep_content_dict.error_msg = STATUS_CODE[code] 
            return prep_content_dict
    if tool.tapered_neck_diameter:
        tapered_neck_prep = True
        if not tool.tapered_neck_angle:
            tool.tapered_neck_angle = PREP_DICT["bur_neck_prep"]["included_prep_angle"]
        if shank_reduction_prep and any(x in split_description for x in ["OVAL", "INVERTED"]): # Type F burs do not have neck on 2nd prep
            tapered_neck_prep = False
    else:
        tapered_neck_prep = False

    prep_tip_dia = 0.0
    point_prep = False
    POINT_PREP_DICT = PREP_DICT["point_prep"] # Tools that always require point prep
    
    if family == "DRILL":
        DRILL_PREP_DICT = PREP_DICT["drill_prep"]
        point_prep_dia_cutoff = DRILL_PREP_DICT["point_prep_dia_cutoff"]
        if "HURRICANE" in description:
            point_prep = True
            tip_percent = POINT_PREP_DICT["prep_tip%"]

        elif cut_dia >= point_prep_dia_cutoff: 
            point_prep = True
            if "DRILL&COUNTERSINK" in description:
                tip_percent = POINT_PREP_DICT["drill&countersink%"]
            else:
                tip_percent = POINT_PREP_DICT["drill%"]

    if any(word in description for word in POINT_PREP_DICT["tools"]) and "DRILL&COUNTERSINK" not in description:
        point_prep = True
        tip_percent = POINT_PREP_DICT["prep_tip%"]
    
    chamfer_prep = False
    radius_prep = False
    if "BALL" in split_description: 
        ball_prep_rules = PREP_DICT["ball_prep"]
        dia_cutoff = ball_prep_rules["dia_cutoff"]
        dia_ref_1 = ball_prep_rules["dia_ref_1"]
        loc_ref_1 = ball_prep_rules["loc_ref_1"]
        dia_ref_2 = ball_prep_rules["dia_ref_2"]
        loc_ref_2 = ball_prep_rules["loc_ref_2"]

        if cut_dia <= dia_cutoff:
            if cut_dia > dia_ref_1 and loc < loc_ref_1:
                chamfer_prep = True
            elif cut_dia >= dia_ref_2 and loc >= loc_ref_2:
                chamfer_prep = True
        elif cut_dia > dia_cutoff:
            radius_prep = True
    
    if "CR" in split_description:
        cr_prep_rules = json_content["prep"]["cr_prep"]
        dia_cutoff = cr_prep_rules["dia_cutoff"]
        cut_percent = cr_prep_rules["cut_%"]

        if cut_dia > dia_cutoff and cr >= cut_percent*cut_dia:
            chamfer_prep = True
    
    if "PILOTED DIEMILL" in description:
        chamfer_prep = True

    if chamfer_prep:
        tool.tip_diameter = cut_dia*0.50
        tool.main_angle = 45.0
    if tool.tip_diameter: # Manually entered tip diameter
        point_prep = True

    if point_prep:
        if not tool.main_angle:
            code = 404
            prep_content_dict.status_code = code
            prep_content_dict.error_msg = "Missing included main angle to calculate point length. "
            return prep_content_dict
        if "BUR" in family:
            if not tool.tip_diameter:
                code = 404
                prep_content_dict.status_code = code
                prep_content_dict.error_msg = "Missing tip diameter to calculate point length (for BUR tools). "
                return prep_content_dict
            else:
                prep_tip_dia = tool.tip_diameter # Assumes tip diameter is already prep tip diameter from manual entry
        if not prep_tip_dia:
            if tool.tip_diameter:
                prep_tip_dia = tool.tip_diameter + .010 # Standard increase for tip prep
            else:
                prep_tip_dia = cut_dia*tip_percent

    print(family)
    
    if "TAPERMILL" in split_description:
        prep_tip_dia = cut_dia
        if "SQ" in split_description or "CR" in split_description:
            prep_tip_dia = cut_dia + .01
        front_reduction_prep = False
        point_prep = True
    bumping_prep = False
    cut_off_prep = False
    if oal != 0 and oal < mat_len: # Checking material dimension compared to tool dimension
        bumping_rule = PREP_DICT["bumping_prep"]
        bumping_max = bumping_rule["length_cutoff"]
        dif = mat_len - oal
        if dif < bumping_max/25.4:
            bumping_prep = True
        else:
            cut_off_prep = True
    else:
        bumping_prep = False # Todo - Handle bumping for burs with cut off and bumping get bumping rates for excel
        cut_off_prep = False

    if "W/FLAT" in split_description:
        flat_prep = True
    else:
        flat_prep = False
    
    

    """if "SOLID" not in mat.upper() and "BUR" in family:
        shank_reduction_prep = False
        point_prep = False
        tapered_neck_prep = False"""
    # ------ Calculations ------
    
    def vol_calc(major_od: float, minor_od: float, height: float, sheet_name="", neck_type = "", vol_type = ""):
        """
        Calculate volume/material removed depending on shape.

        Parameters:
        major_od (float): Major outer diameter of the part.
        minor_od (float): Minor outer diameter of the part.
        height (float): Length of the maeterial removed.
        sheet_name (str): Name of the sheet in the excel file.
        neck_type (str): Type of neck (Before Fluting or After Fluting).
        vol_type (str): Type of volume (CYLINDER or CONE).

        Returns:
        ContentDict: Dictionary containing time, reduction_vol, and rate.
        """
        LENGTH_RATIO = "length_ratio"
        NECK_RATIO = "neck_ratio"

        vol_content_dict = ContentDict(
            status_code = 900, 
            error_msg = "", 
            function = "vol_calc",
            content = {'time': 0.0,'reduction_vol': 0.0,'rate': 0.0}
        )
        
        excel = excel_layer.content['excel']
        fr_df = pd.DataFrame(excel[sheet_name])
        if len(fr_df) == 0:
            code = 404
            vol_content_dict.status_code = code
            vol_content_dict.error_msg = f"Code {code}: {sheet_name} is empty"
            return vol_content_dict
        # Check for nan values
        if fr_df.isnull().values.any():
            code = 102
            vol_content_dict.status_code = code
            vol_content_dict.error_msg = STATUS_CODE[code] + " " + vol_content_dict.function
            return vol_content_dict
        
        rate = 0.0
        major_rad = major_od/2
        minor_rad = minor_od/2
        
        major_vol = pi * (major_rad**2)*height
        if vol_type == "CYLINDER":
            minor_vol = pi * (minor_rad**2)*height
        if vol_type == "CONE":
            minor_vol = (pi*height*(major_rad**2 + minor_rad**2 + major_rad*minor_rad))/3 # Volume of truncated cone
        reduction_vol = major_vol - minor_vol
        length_ratio = round(height/minor_od, 0)
        match_row = pd.DataFrame()
        if sheet_name == "F_RED_PREP":
            
            if length_ratio < 8:
                under_8_df = fr_df[fr_df[LENGTH_RATIO] < 8]
                match_idx = (under_8_df['reduction_vol'] - reduction_vol).abs().idxmin()
                match_row = under_8_df.loc[match_idx]

            else:
                over_8_df = fr_df[fr_df[LENGTH_RATIO] >= 8]
                match_idx = (over_8_df['reduction_vol'] - reduction_vol).abs().idxmin()
                match_row = over_8_df.loc[match_idx]

        if sheet_name == "NECK_PREP": 
            neck_pecent = 1-(minor_od/major_od)
            if minor_od == major_od: 
                allowed_percent = 0.15
            else:
                allowed_percent = 0.2 # Accounts for neck preps that happend after fluting due to prep dia increase
            if neck_pecent < allowed_percent:
                neck_df = fr_df[fr_df[NECK_RATIO] < 0.15]
            else:
                neck_df = fr_df[fr_df[NECK_RATIO] >= 0.15]
            
            if length_ratio < 8:
                under_8_df = neck_df[neck_df[LENGTH_RATIO] < 8]
                match_idx = (under_8_df['reduction_vol'] - reduction_vol).abs().idxmin()
                match_row = under_8_df.loc[match_idx]
            else:
                over_8_df = neck_df[neck_df[LENGTH_RATIO] >= 8]
                match_idx = (over_8_df['reduction_vol'] - reduction_vol).abs().idxmin()
                match_row = over_8_df.loc[match_idx]
        
        if sheet_name == "POINT_PREP":
            # Find closest match angle
            closest_diameter = float(min(fr_df["major_diameter"], key=lambda x: abs(x - major_od)))
            match_row = fr_df[fr_df["major_diameter"] == closest_diameter]
            tip_ratio = minor_od/major_od
            length_ratio = round(height/major_od, 1)
            inc = 1.0
            if tip_ratio >= .45:
                inc = 1.1
            if "TAPERMILL" in tool.tool_description and height/minor_od > 8:
                inc += 1.6 # Speeds up longer tapermill preps
            
            rate = float(match_row["in^3_per_min"].values[0])*inc

        else: 
            rate =match_row["in^3_per_min"]

        """ if neck_type == "BF":
            rate = rate * 0.7"""
        if not rate: # type: ignore
            time = 0
        else:
            time =(reduction_vol / rate).__round__(3)
        
        vol_content_dict.content["time"] = time
        vol_content_dict.content["reduction_vol"] = reduction_vol
        vol_content_dict.content["rate"] = rate
        return vol_content_dict

    # Shank Reduction Calculations
    shank_length = oal-loc # Default shank length calculation
    
    if shank_reduction_prep:
        sr_info = vol_calc(cut_dia, shank_dia, shank_length, sheet_name="F_RED_PREP", vol_type="CYLINDER")
        if sr_info.status_code != 900:
            return sr_info
        sr_time = sr_info.content["time"]
        sr_reduction_vol = sr_info.content["reduction_vol"]
        sr_rate = sr_info.content["rate"]
    else:
        sr_time = 0.0
        sr_reduction_vol = 0.0
        sr_rate = 0.0

    # Neck prep Calculations
    if neck_prep:
        reach = nk_len + loc
        reach_ratio = round(reach/cut_dia, 0)
        if front_reduction_prep == True:
            if shank_dia <= .1250: # Neck type conditions
                if reach_ratio > 6.0:
                    if cut_dia >= .035:
                        nk_type = "AF" # After Fluting
            elif shank_dia <= .2500:
                if reach_ratio > 7.0: # Larger neck diameter
                    nk_type = "AF" 
        if nk_type == "AF": # Neck reduced from shank diameter
            base_dia = shank_dia 
        else:
            base_dia = prep_dia
            
        nk_info = vol_calc(base_dia, nk_dia, nk_len, sheet_name="NECK_PREP", vol_type="CYLINDER")
        
        if nk_info.status_code != 900:
            return nk_info
        nk_time = float(nk_info.content["time"])
        nk_reduction_vol = float(nk_info.content["reduction_vol"])
        nk_rate = float(nk_info.content["rate"])
    else:
        nk_time = 0.0
        nk_reduction_vol = 0.0
        nk_rate = 0.0

    # Front reduction calculations
    if front_reduction_prep: 
        if neck_prep and nk_type == "BF": # If neck prep is needed, reducing neck length and loc
            fr_info = vol_calc(shank_dia, prep_dia, reach, sheet_name="F_RED_PREP", neck_type = nk_type, vol_type="CYLINDER")
        else:
            fr_info = vol_calc(shank_dia, prep_dia, prep_length, sheet_name="F_RED_PREP", vol_type="CYLINDER")

        if fr_info.status_code != 900:
            return fr_info
        fr_time = float(fr_info.content["time"])
        fr_reduction_vol = float(fr_info.content["reduction_vol"])
        fr_rate = float(fr_info.content["rate"])
    else:
        fr_time = 0.0
        fr_reduction_vol = 0.0
        fr_rate = 0.0

    # Point Prep Calculations
    if point_prep:
        base_dia = shank_dia
        if front_reduction_prep or shank_reduction_prep:
            base_dia = prep_dia
        cone_tip_length = find_height_tan(tool.main_angle, prep_tip_dia)
        truncated_cone_length = find_height_tan(tool.main_angle, base_dia) - cone_tip_length

        pt_info = vol_calc(base_dia, prep_tip_dia, truncated_cone_length, sheet_name="POINT_PREP", vol_type="CONE")
        if pt_info.status_code != 900:
            return pt_info
        pt_time = float(pt_info.content["time"])
        pt_reduction_vol = float(pt_info.content["reduction_vol"])
        pt_rate = float(pt_info.content["rate"])
    else:
        pt_time = 0.0
        pt_reduction_vol = 0.0
        pt_rate = 0.0
    """def find_base_tan(angle, height):
        if angle == 90.0:
            angle = 90.0/2.0
        else:
            angle = 90.0 - (angle/2.0)
        base = (height/tan(radians(angle)))*2
        return base"""
    
    # Tapered Neck Calculations
    if tapered_neck_prep:
        if tool.neck_length:
            #base_dia = find_base_tan(tool.tapered_neck_angle, tool.neck_length) + tool.tapered_neck_diameter
            base_dia = shank_dia
            tip_dia = tool.tapered_neck_diameter
            truncated_cone_length = nk_len
        else:
            base_dia = shank_dia
            tip_dia = tool.tapered_neck_diameter
            cone_tip_length = find_height_tan(tool.tapered_neck_angle,tool.tapered_neck_diameter)
            truncated_cone_length = find_height_tan(tool.tapered_neck_angle, base_dia) - cone_tip_length
        
        tp_nk_info = vol_calc(base_dia, tip_dia, truncated_cone_length, sheet_name="POINT_PREP", vol_type="CONE")
        if tp_nk_info.status_code != 900:
            return tp_nk_info
        tp_nk_time = float(tp_nk_info.content["time"])
        tp_nk_reduction_vol = float(tp_nk_info.content["reduction_vol"])
        tp_nk_rate = float(tp_nk_info.content["rate"])
    else:
        tp_nk_time = 0.0
        tp_nk_reduction_vol = 0.0
        tp_nk_rate = 0.0
    inc_percentage = 1.10 
    prep_type_dict = {
        "Front Reduction Prep": (front_reduction_prep, round(fr_time*inc_percentage,4), fr_reduction_vol, fr_rate),
        "Shank Reduction Prep": (shank_reduction_prep, round(sr_time*inc_percentage,4), sr_reduction_vol, sr_rate),
        "Point Prep": (point_prep, round(pt_time*inc_percentage,4),pt_reduction_vol, pt_rate),
        "Chamfer Prep": (chamfer_prep, 0.0, 0.0, 0.0),
        "Neck Prep": (neck_prep, round(nk_time*inc_percentage,4), nk_reduction_vol, nk_rate),
        "Tapered Neck Prep": (tapered_neck_prep, round(tp_nk_time*inc_percentage,4), tp_nk_reduction_vol, tp_nk_rate),
        "Radius Prep": (radius_prep, 0.0, 0.0, 0.0),
        "Backtaper Prep": (backtaper_prep, round(bt_time*inc_percentage,4), 0.0, backtaper_rate),
        "Flat Prep": (flat_prep, 0.0, 0.0, 0.0),
        "Cut Off Prep": (cut_off_prep, 0.0, 0.0, 0.0),
        "Bumping Prep": (bumping_prep, 0.0, 0.0, 0.0),
        "Centerless Grinding Prep": (cg_prep, 0.0, 0.0, 0.0)
    }
    
    if neck_prep:
        dict = {
            "AF": "After Fluting",
            "BF": "Before Fluting",
        }
        nk_type = dict[nk_type]
        prep_type_dict["Neck Prep (" + nk_type + ")"] = prep_type_dict.pop("Neck Prep")
    prep_type = [(key, value[1], value[2], value[3]) for key, value in prep_type_dict.items() if value[0] == True] # Get prep type if prep is needed
    #Sum up the prep time
    total_prep_time = 0.0
    total_robot_time = 0.0
    robot_time = 0.0
    for prep in prep_type:
        time = prep[1]
        if time < 1.11 and not time == 0.0:
            if "Backtaper Prep" in prep[0]:
                robot_time = round(5/60, 4) #5 seconds
            else:
                robot_time = round(20/60, 4) #20 seconds
        else:
            robot_time = 0.0
        prep_time = round(time + robot_time, 3)
        total_robot_time += robot_time
        total_prep_time += prep_time

    if double_end:
        total_prep_time = total_prep_time * 2

    total_prep_time = round(total_prep_time + robot_time, 3)
    prep_type_text = str()
    if prep_type != []:
        for pair in prep_type:
            prep_type_text += pair[0] + f": {pair[1]} | "
    if prep_type_text[-3:] == " | ":
        prep_type_text = prep_type_text[:-3]
    
    if prep_type != []:
        prep_type_text += f" | Robot Time: {robot_time}"
        tool.prep_type = prep_type_text
        tool.prep_cycle_time = total_prep_time
    return prep_content_dict

def get_tool_detail(tool: ToolInfo, context=None, **kwargs):
    feature = InputArgData()
    td_content_dict = ContentDict(
        status_code=900, 
        error_msg="", 
        function="get_tool_detail", 
        content={
            "tool": tool, 
            "feature": feature}
        )
    if kwargs:
        args = kwargs.get('args', [])
        for arg in args:
            attr = {
                "TERT": "tert_od_angle", 
                "NOTCH": "notch", 
                "DE": "double_end", 
                "COARSE": "coarse",
                "DETAIL": "detail", 
                "MASS": "mass_detail", 
                "MM": "mm", 
                "PREP": "prep"
            }.get(arg.upper())
            if attr:
                setattr(feature, attr, True)
        kw = kwargs.get('kwargs', {})
        for k, v in kw.items():
            attr = {
                "PART_NUM": "part_number", 
                "MATERIAL": "material", 
                "MAT_DIMENSION": "material_dimension",
                "TIP_DIAMETER": "tip_diameter", 
                "TAPERED_NECK_DIA": "tapered_neck_diameter"
            }.get(k.upper())
            if attr:
                try:
                    setattr(tool, attr, type(getattr(tool, attr))(v))
                except Exception as e:
                    td_content_dict.status_code = 200
                    td_content_dict.error_msg = f"{STATUS_CODE[200]} Error with kwarg {k}: {e}"
                    return td_content_dict
                
    var_dict = parse_description(tool, context, using_mm=feature.mm, prep=feature.prep)
    if var_dict.status_code != 900:
        return var_dict
    json_content, tool = var_dict.content.values()

    try:
        cut_dia = float(tool.cut_diameter)
        loc = float(tool.length_of_cut)
        shank_dia = float(tool.shank_diameter)
        oal = float(tool.overall_length)
        description = str(tool.tool_description)
    except ValueError as e:
        code = 201
        td_content_dict.status_code = code
        td_content_dict.error_msg = STATUS_CODE[code] + f"--{str(e)}"
        return td_content_dict
    if tool.material_dimension:
        try:
            dims = tool.material_dimension.upper().replace("-", "+").split("X")
            mat_dim = [float(eval(d)) for d in dims]
            if mat_dim[1] > MM_CUTOFF:
                mat_dim = [d/25.4 for d in mat_dim]
            tool.material_diameter, tool.material_oal = mat_dim
        except Exception as e:
            td_content_dict.status_code = 200
            td_content_dict.error_msg = f"{STATUS_CODE[200]} Material dimension: {e}"
            return td_content_dict
    else:
        tool.material_diameter, tool.material_oal = cut_dia, oal
    
    global PERF_LIST
    PERF_LIST = json_content["perf_series"] # High performance endmills
    HAS_END_TIME = json_content[JSON_DICT_NAME]["has_end_time"] # List with wood router description to indicate if it has end/gash time
    base_description = tool.formatted_description
    split_description = description.split(" ")

    if "DRILL&COUNTERSINK" in split_description:
        feature.double_end = True
    if "CC" in split_description:
        feature.coarse = True
    if "DE" in split_description:
        feature.double_end = True

    family_dict = get_family(json_content, base_description, split_description)
    if family_dict.status_code != 900:
        return family_dict
    
    family_dict = family_dict.content
    tool.tool_family = family_dict["family"]
    tool.reference_family = family_dict["ref_family"]
    feature.end_type = family_dict["end_type"]
    feature.bur_cut = family_dict["bur_cut"]
    feature.spiral = family_dict["spiral"]
    
    chk_list = [cut_dia, loc, shank_dia, description]
    if any(var == "" or var == 0 for var in chk_list):
        code = 206
        td_content_dict.status_code = code
        td_content_dict.error_msg = STATUS_CODE[code]
        return td_content_dict
    if tool.tool_family in ROUTER_FAM:
        feature.notch = False
        if tool.flute_count == "1":
            tool.flute_count = "2" # All wood routers with 1 flute are treated as if they have 2 flutes
        feature.end_time = any(desc in HAS_END_TIME for desc in split_description)

    feature.performance = any(ps in description for ps in PERF_LIST)

    if feature.prep: 
        prep_dict = calc_prep_time(tool=tool, context=context, parse=False, double_end=feature.double_end)
        if prep_dict.status_code != 900:
            return prep_dict
        
        tool = prep_dict.content['tool']

    fluting_dict = calc_fluting_time(tool, feature, context)
    if fluting_dict.status_code != 900:
        return fluting_dict
    tool = fluting_dict.content['tool']
    feature = fluting_dict.content['feature']

    td_content_dict.content = {"tool": tool, "feature": feature, "detail": fluting_dict.content['detail']}
    return td_content_dict
def calc_fluting_time(tool: ToolInfo, feature: InputArgData,  context=None):
    ft_content_dict = ContentDict(
        status_code=900,
        error_msg="", 
        function="calc_fluting_time", 
        content={}
        )
    fl_cnt = tool.flute_count
    ref_fam = tool.reference_family
    try:
        if "/" in str(fl_cnt):
            fl_cnt1, fl_cnt2 = map(int, fl_cnt.split("/"))
        elif fl_cnt != "":
            fl_cnt1, fl_cnt2 = int(fl_cnt), 1
        else:
            code = 307
            ft_content_dict.status_code = code
            ft_content_dict.error_msg = STATUS_CODE[code]
            return ft_content_dict
    except Exception as e:
        code = 202 if "/" in str(fl_cnt) else 203
        ft_content_dict.status_code = code
        ft_content_dict.error_msg = STATUS_CODE[code] + f" {e}"
        return ft_content_dict
    
    excel_data = get_xlsx_from_layer(context) 
    if excel_data.status_code != 900:
        return excel_data
    
    fluting_fr_data = excel_data.content['excel']
    actual_time = 0
    double_end = feature.double_end
    part_num = tool.part_number
    if feature.mass_detail: # Multiple items from excel sheet
        import datetime as dt
        
        live_time_df = pd.DataFrame(fluting_fr_data["Bur Live Time"])
        if live_time_df.empty:
            code = 105
            ft_content_dict.status_code = code
            ft_content_dict.error_msg = STATUS_CODE[code]
            return ft_content_dict
        else:
            actual_time = live_time_df.loc[live_time_df['program'] == part_num, 'cycle_avg2'].values[0] if live_time_df['program'].eq(part_num).any() else dt.time(0,0,0)

        if double_end:
            actual_time_in_seconds = actual_time.hour * 3600 + actual_time.minute * 60 + actual_time.second
            actual_time_in_seconds *= 2
            actual_time = dt.time(actual_time_in_seconds // 3600, (actual_time_in_seconds % 3600) // 60, actual_time_in_seconds % 60)
    
    fluting_fr_data = pd.DataFrame(fluting_fr_data[ref_fam]) # Get excel sheet to use for calculations
    
    filtered_df = pd.DataFrame()
    family = tool.tool_family
    split_description = tool.tool_description.split(" ")
    description = tool.formatted_description
    cut_dia = tool.cut_diameter
    # Concise filtering for tool family/fluting data
    if family == "FBGR" or "DIEMILL" in split_description or "TIRE BUR" in description:
        shapes = ["CYLINDER NOENDCUT"]
        if "TIRE BUR" in description:
            shapes.append("INCLUDED POINTED CONE")
        filtered_df = fluting_fr_data[
            (fluting_fr_data["min_diameter"].astype(float) <= cut_dia) &
            (fluting_fr_data["max_diameter"].astype(float) >= cut_dia) &
            (fluting_fr_data["bur_type"].astype(str).isin(shapes))
        ]
    elif family == "BUR":
        description = tool.bur_description
        match = next((s for s in fluting_fr_data["bur_type"].unique() if s.upper() in description), None)
        if match:
            filtered_df = fluting_fr_data[
                (fluting_fr_data["min_diameter"].astype(float) <= cut_dia) &
                (fluting_fr_data["max_diameter"].astype(float) >= cut_dia) &
                (fluting_fr_data["bur_type"].astype(str) == str(match))
            ]
        else:
            code = 304
            ft_content_dict.status_code = code
            ft_content_dict.error_msg = STATUS_CODE[code] + f" {tool.bur_description}"
            return ft_content_dict
    else:
        if family == "DRILL" and cut_dia > 0.8500:
            cut_dia = 0.850
        filtered_df = fluting_fr_data[
            (fluting_fr_data["min_diameter"].astype(float) <= cut_dia) &
            (fluting_fr_data["max_diameter"].astype(float) >= cut_dia)
        ]
    if filtered_df.empty:
        code = 305
        ft_content_dict.status_code = code
        ft_content_dict.error_msg = STATUS_CODE[code]
        return ft_content_dict
    row_values = filtered_df.iloc[0]
    inc_percentage = 1
    inc_per_tracker = [float(), str()] # Tracks increases made to percentage and why
    num = 0.0
    fluting_feedrate = 0.0
    od_feedrate = 0.0
    end_cycle_time = 0.0
    end_gash_cycle_time = 0.0
    end_split_time = 0.0
    end_time = True
    fluting_time = 0.0
    calc_fl_time = 0.0
    calc_od_time = 0.0
    calc_end_time = 0.0
    calc_gash_time = 0.0
    
    sc_time = 0.0
    dc_time = 0.0
    sc_fluting_feedrate = 0.0
    dc_fluting_feedrate = 0.0  
    
    dia_cutoff = round(3/25.4, 4)

    loc = org_loc = tool.length_of_cut
    shank_dia = tool.shank_diameter
    oal = tool.overall_length
    if ref_fam == "BUR":
        """--------------------------------------------------------------------------------------------------------------
                                                        BUR CALCULATIONS
        --------------------------------------------------------------------------------------------------------------"""
        mf_inc = chk_mirror_finish(inc_percentage, split_description)
        if mf_inc > inc_percentage:
            num = mf_inc - inc_percentage
            inc_percentage += num
            inc_per_tracker.append((num, "Mirror Finish"))
        if "TIRE BUR" in description: # Join two rows in filtered dataframe to get feedrates for tire burs
            loc = loc/5 # Uses SA + SM but it is a bit of a hassle to calculate each individual component (Cylindrical + Cone)
            if cut_dia >= 0.5:
                num = 0.15
                inc_percentage += num
                inc_per_tracker.append((num, "cut_dia >= 0.5"))
            row_values = filtered_df.iloc[0] + filtered_df.iloc[1]

        sc_fluting_feedrate = row_values["sc_fluting"]
        dc_fluting_feedrate = row_values["dc_fluting"]

        if feature.spiral:
            num = 0.10
            inc_percentage += num
            inc_per_tracker.append((num, "Spiral"))

        if feature.bur_cut not in ["FM", "NX"] or family == "FBGR":
            sc_time = sc_fluting_feedrate * loc * fl_cnt1 * inc_percentage
            dc_fl_check = ["DM", "DC", "FBGR"] # Tools that must have sc/dc flutes
            if fl_cnt2 == 1 and re.search(r'\b(?:' + '|'.join(dc_fl_check) + r')\b', description):
                code = 306
                ft_content_dict.status_code = code
                ft_content_dict.error_msg = STATUS_CODE[code]
                return ft_content_dict
            dc_time = (dc_fluting_feedrate * loc * fl_cnt2 * inc_percentage if "SC" not in split_description or family == "FBGR" else 0)
            fluting_time = sc_time + dc_time

        if feature.bur_cut in ["FM", "NX"] or family == "FBGR": # Treated like endmills 
            # Adjust inc_percentage for special cases
            if "COUNTERSINK" in description: # For countersinks that are not bur
                num = 0.20
                inc_percentage += num
                inc_per_tracker.append((num, "Countersink"))
                if cut_dia > 0.3700:
                    num = (cut_dia/loc)-0.15
                    inc_percentage += (cut_dia / loc) - 0.15
                    inc_per_tracker.append((num, "cut_dia > 0.3700"))
            elif "INCLUDED CONE" in description and loc < .22:
                num = (1 - (loc / .22)) + .1
                inc_percentage += num
                inc_per_tracker.append((num, "loc < 0.22"))
                if fl_cnt1 < 6:
                    num = 0.25
                    inc_percentage += num
                    inc_per_tracker.append((num, "flute count < 6"))

            fluting_feedrate = row_values["fluting_fr"]
            od_feedrate = row_values["od_fr"]
            end_cycle_time = row_values["end_ct"]
            end_gash_cycle_time = row_values["end_gash_ct"]
            end_split_time = row_values["end_split_ct"]

            if family == "FBGR":
                fluting_feedrate = od_feedrate = end_split_time = 0
                if feature.end_type in ["PLAIN", "BUR", "FISHTAIL"]:
                    end_gash_cycle_time = 0
                    if feature.end_type == "PLAIN":
                        end_cycle_time = 0

            # Muraki FM without notch
            if (part_num.startswith("AC") or part_num.startswith("TA")) and part_num.endswith("FM") and not feature.notch:
                end_split_time *= .45
            if cut_dia >= .748:
                num = 0.12
                inc_percentage += num
                inc_per_tracker.append((num, "cut_dia >= 0.748"))

            # Calculate times, avoid division by zero
            calc_gash_time = ((cut_dia * .5) / end_gash_cycle_time) * fl_cnt1 * inc_percentage if end_gash_cycle_time else 0
            calc_end_time = ((cut_dia * .5) / end_cycle_time) * fl_cnt1 * inc_percentage if end_cycle_time else 0
            calc_fl_time = (loc / fluting_feedrate) * fl_cnt1 * inc_percentage if fluting_feedrate else 0
            calc_od_time = (loc / od_feedrate) * fl_cnt1 * inc_percentage if od_feedrate else 0
            
            fluting_time = calc_fl_time + calc_od_time + calc_end_time + calc_gash_time + end_split_time
            if family == "FBGR":
                fluting_time = calc_fl_time + calc_od_time + calc_end_time + calc_gash_time + end_split_time + sc_time + dc_time
        if double_end == True:
            fluting_time *= 2
        if "~" in description:
            description = description.split("~")[0].rstrip()  

        detail_print = ''.join([
            f"Tool Type: {description}\n",
            f"Diameter: {round(cut_dia, 4)}\n",
            f"Length of Cut: {round(org_loc, 4)}\n",
            f"Shank Diameter: {round(shank_dia, 4)}\n",
            f"OAL: {round(oal, 4)}\n",
            f"Flute Count: {fl_cnt}\n",
            f"Cycle Time: {round(fluting_time, 3)}\n",
            f"Increase Percentage: {round((inc_percentage-1)*100, 2)}%\n",
            "\n------Base Cycle Times------\n",
            *(f"{name}: {round(val, 2)}\n" for name, val in [
                ("Single Cut Time", sc_time),
                ("Double Cut Time", dc_time),
                ("Fluting Feedrate", calc_fl_time),
                ("OD Feedrate", calc_od_time),
                ("End Gash Time", calc_end_time),
                ("End Cycle Time", calc_gash_time),
                ("End Split Time", end_split_time)
            ] if val != 0)
        ])
        feature_list = (fluting_time, inc_percentage, actual_time, sc_time, dc_time, calc_fl_time, calc_od_time, calc_end_time, calc_gash_time, end_split_time)
    
    if any(fam in ref_fam for fam in ["EM", "WR", "O-FLUTE", "WR COMP", "DRILL"]):
        """--------------------------------------------------------------------------------------------------------------
                                ENDMILL/ WOOD ROUTER/ O-FLUTE CALCULATIONS/ COMPRESSION ROUTER/ DRILL
        --------------------------------------------------------------------------------------------------------------"""
        sec_inc = 0.0
        split = feature.notch
        tert_od_angle = feature.tert_od_angle
        
        dynamic_variable = 2.5 # Change value to adjust cycle time to be more precise
        if "MINI-MILL" in description.upper():
            mm_ratio = cut_dia/loc
            if mm_ratio > 0.5:
                loc *= 1.8
                
        if "OFX" in description:
            split_description.append("MF")
            if cut_dia > 0.079:
                num = 0.20
                inc_percentage += num
                inc_per_tracker.append((num, "OFX > 0.079"))

        mf_inc = chk_mirror_finish(inc_percentage, split_description)
        if mf_inc > inc_percentage:
            num = mf_inc - inc_percentage
            inc_percentage += num
            inc_per_tracker.append((num, "Mirror Finish"))
            
        if "STAGGERED" in description:
            loc = cut_dia*3
        
        if cut_dia < 0.06:
            diff = cut_dia/row_values["max_diameter"]
        else:
            diff = 1.0
        fluting_feedrate = row_values["fluting_fr"]*diff
        od_feedrate = row_values["od_fr"]*diff
        end_cycle_time = row_values["end_ct"]
        end_gash_cycle_time = row_values["end_gash_ct"]
        end_split_time = row_values["end_split_ct"]
        end_time = feature.end_time

        # 2 flute case accounting for passes
        if fl_cnt1 == 2:
            cnt = 4
            """if diameter < dia_cutoff and family == "DRILL":
                cnt = 2"""
            
            calc_fl_time = float((loc/fluting_feedrate)*dynamic_variable*cnt)
            calc_od_time = float((loc/od_feedrate)*dynamic_variable*cnt)  # OD Cycle time
        else:
            calc_fl_time = float((loc/fluting_feedrate)*dynamic_variable*fl_cnt1) # Fluting Cycle time
            calc_od_time = float((loc/od_feedrate)*dynamic_variable*fl_cnt1)  # OD Cycle time

        calc_end_time = float(((cut_dia*.5)/end_cycle_time)*dynamic_variable*fl_cnt1) # End Cycle time
        calc_gash_time = float(((cut_dia*.5)/end_gash_cycle_time)*dynamic_variable*fl_cnt1) # Gash Cycle time
        # Check if tool type in performance series and adjust cycle time by increased percentage
        def check_performance_series(tool_type, inc_percentage, split, sec_od_angle, sec_inc):
            for ps in PERF_LIST:
                if ps in tool_type:
                    if ps.startswith("V"):
                        inc_percentage += 0.1
                        if tool_type.startswith("SQ") or tool_type.startswith("CR"):
                            split = False
                        #sec_od_angle = False
                    elif ps == "AX":
                        inc_percentage += 0.05
                        split = False
                        if "CB" in tool_type:
                            sec_inc = 45/60 # 45secs or 0.75min
                    elif ps == "CR TAPERMILL":
                        # Split taken care of by standard case
                        # Only corner radius tapermill are considered high perfomance
                        inc_percentage -= 0.15 # Using percentage similar to V4
                        #sec_od_angle = False
                    elif ps == "F45":
                        split = False
                        inc_percentage += 0.1
                        #sec_od_angle = False
                    elif ps == "HY5":
                        # Split taken care of by standard case
                        inc_percentage += 0.1
                        #sec_od_angle = True
                    elif ps == "HYPERMILL":
                        # Split taken care of by standard case
                        inc_percentage += 0.05
                        #sec_od_angle = True
                    elif ps == "MOLD":
                        # Split taken care of by standard case
                        inc_percentage += 0.05
                    elif ps == "TWISTER":
                        # Split taken care of by standard case
                        inc_percentage += 0.05
                        #sec_od_angle = True
            return inc_percentage, split, sec_od_angle, sec_inc
        
                # Standard tools will follow and other are accounted for when checking tool type
        
        if cut_dia < dia_cutoff:
            sec_od_angle = False
        else:
            sec_od_angle = True
        """ Dictonary for tools with split base on flutes for standard endmills """
        SPLIT_DICT = {
            "SQ EM": [3,5,6],
            "BALL EM": [3,4,5,6],
            "CR EM": [3,5,6],
            "ROUGHER EM": [3,5,6],
            "TAPERMILL EM": [3],
            "NONE": []
            }
        EM_MAP = {
            "SQ": ("SQ EM", 0.0, sec_od_angle),
            "BALL": ("BALL EM", 0.25, sec_od_angle),
            "CR": ("CR EM", 0.20, sec_od_angle),
            "DRILLMILL": ("NONE", 0.05, sec_od_angle),
            "ROUGHER": ("ROUGHER EM", 0.0, False),
            "ALUMAZIP": ("NONE", 0.0, False),
            "TAPERMILL": ("TAPERMILL EM", 0.0 if "CR" in description else 0.05, True)
        }
        for word, (split_key, inc, sec_od) in EM_MAP.items():
            if description.startswith(word) or word in description:
                inc_percentage += inc
                if fl_cnt1 in SPLIT_DICT[split_key]:
                    split = True
                else:
                    split = False
                sec_od_angle = sec_od
        
        if "ROUGHER" in description.upper():
            sec_inc = 60/60 # 60secs or 1min

        if "STRFL" in description.upper() and not "REAMER" in description: # Straight Flute
            inc_percentage += 0.1
            if family == "DRILL":
                inc_percentage += 0.45
        
        if family in ROUTER_FAM: # Wood Routers
            if "CB" in description.upper(): # Chipbreaker
                inc_percentage += 0.20

            if "COMP" in description: # Compression
                if fl_cnt1 == 2:
                    inc_percentage += 0.5
                else:
                    inc_percentage += 0.70
        
            if "HOGGER" in description.upper() or "RIPPER" in description.upper():
                inc_percentage += 0.40

        if "REAMER" in description:
            if "ENDCUT" in description:
                end_time = True
            else:
                end_time = False
        elif family == "DRILL":
            split = False
            calc_od_time = 0.0
            
            if "SPADE" in description:
                # 5mm/min fluting feed rate
                calc_fl_time = float(loc/(5/25.4))
                
                inc_percentage += 0.30
                if cut_dia < 0.1575:
                    inc_percentage += 0.15
                calc_gash_time = 0.0
            
            else:
                if cut_dia < dia_cutoff:
                    inc_percentage -= 0.20 # Drills under 3mm speed up cycle time
                    if cut_dia < 0.0501: 
                        inc_percentage -= 0.30 # Minatures times are too slow - decreasing time
                    calc_gash_time = 0.0

                if "SPOTTING" in description:
                    inc_percentage += 0.20
                elif "DRILL&COUNTERSINK" in description:
                    if cut_dia > 0.0500:
                        inc_percentage += 0.15
                elif "HURRICANE" in description:
                    inc_percentage += 0.20
                elif "MAXIMIZER" in description:
                    inc_percentage += 0.15

                if loc < 0.7000 and cut_dia > 0.0790 and "SPOTTING" not in description: # Shorter lengths too fast - slowing down
                    inc_percentage += 0.15
                if cut_dia > 0.5000:
                    inc_percentage -= 0.05
        if feature.performance:
            inc_percentage, split, sec_od_angle, sec_inc = check_performance_series(description, inc_percentage, split, sec_od_angle, sec_inc)

        if tert_od_angle == True and sec_od_angle == False:
            tert_od_angle = False
        # Tools with no od angle
        if calc_od_time == 0.0:
            sec_od_angle = False
            tert_od_angle = False
        if "STAGGERED" in description.upper():
            sec_od_angle = False
            tert_od_angle = False
            split = False
            calc_od_time = 0.0

        if not end_time:
            calc_end_time = 0.0
            calc_gash_time = 0.0
        if not split:
            end_split_time = 0.0          
        if sec_od_angle and tert_od_angle:
            calc_od_time *= 3.0
        elif sec_od_angle and not tert_od_angle:
            calc_od_time *= 2.0
        
        fluting_time = ((calc_fl_time + calc_od_time + calc_end_time + calc_gash_time + end_split_time)*inc_percentage) + (sec_inc*fl_cnt1)

        if double_end == True:
            fluting_time *= 2

        if "MINI-MILL" in description.upper():
            mm_ratio = cut_dia/loc
            if mm_ratio > 0.5:
                mill_inc = 2 + (.6-mm_ratio)
                fluting_time *= mill_inc

        fl_cnt = fl_cnt1
        feature_list = (fluting_time, inc_percentage, actual_time, calc_fl_time, calc_od_time, calc_end_time, calc_gash_time, end_split_time, sec_inc)
        detail_print = ''.join([
            f"Tool Type: {description}\n",
            f"Diameter: {round(cut_dia, 4)}\n",
            f"Length of Cut: {round(org_loc, 4)}\n",
            f"Shank Diameter: {round(shank_dia, 4)}\n",
            f"OAL: {round(oal, 4)}\n",
            f"Flute Count: {fl_cnt1}\n",
            f"\nCycle Time: {round(fluting_time, 3)}\n",
            f"Increase Percentage: {round((inc_percentage-1)*100,2)}%\n",
            f"{'' if sec_inc == 0 else f"Seconds Increase: {sec_inc} min per flute\n"}",
            f"\n------Features------\n",
            f"{'' if not sec_od_angle else 'Has Second OD Angle\n'}",
            f"{'' if not split else 'Has Split/Notch\n'}",
            f"{'' if not tert_od_angle else 'Has Tertiary OD Angle\n'}",
            f"\n------Base Cycle Times------\n",
            *(f"{name}: {round(val, 2)}\n" for name, val in [
                ("Fluting Feedrate", calc_fl_time),
                ("OD Feedrate", calc_od_time),
                ("End Gash Time", calc_end_time),
                ("End Cycle Time", calc_gash_time),
                ("End Split Time", end_split_time)
            ] if val != 0)
        ])
    fluting_time = round(float(fluting_time), 3)
    tool.fluting_cycle_time = fluting_time
    ft_content_dict.content = {"detail": detail_print, "tool": tool, "feature": feature}
    if fluting_time == 0.0:
        code = 401
        ft_content_dict.status_code = code
        ft_content_dict.error_msg = STATUS_CODE[code]
        return ft_content_dict
    if feature.detail == True:
        ft_content_dict.content['detail'] = detail_print
    elif feature.mass_detail == True:
        ft_content_dict.content['detail'] = feature_list
    else:
        ft_content_dict.content['detail'] = description
    return ft_content_dict
if __name__ == "__main__":
    start_time = time.time()
    event = {
        "Diameter": "",
        "LOC": "",
        "ShankDiameter": "",
        "OAL": "",
        "FluteCount": "12/7",
        "Description": '3X11X3X38 14° INCLUDED POINTED CONE DOUBLECUT',
        "args": [],
        "kwargs": {
            "part_num": "DM311-028-5",
            "MATERIAL": "solid", 
            "mat_dimension": ".5x3", 
            "tip_diameter": "0", 
            "tapered_neck_dia": "0"
            }
    }
    context = None
    print(lambda_handler(event, context))
    
    end_time = time.time()
    print(f"\nExecution time: {end_time - start_time} seconds")