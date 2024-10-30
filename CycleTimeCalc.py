# nuitka is used to compile the gui to an executable
# nuitka-project: --disable-console
# nuitka-project: --standalone
# nuitka-project: --enable-plugin=tk-inter

import tkinter # For GUI
from tkinter import ttk
from ttkwidgets.autocomplete import AutocompleteCombobox
from tkinter import messagebox
import pandas as pd
import os
def main():
    global mass_calc
    mass_calc = False
    perf_series = ["V4","V5","V7","AX","F45","HY5","HYPERMILL","MOLD","TWISTER"]
    tool_types_list = [
                #-- Endmill Types ---,
                "DRILLMILL EM", "ROUGHER EM", # Standard endmills
                "SQ EM", "SQ ALUMAZIP EM", "SQ TAPERMILL EM", # Standard endmills
                "SQ V4 EM","SQ V5 EM", "SQ V7 EM", "SQ AX EM", "SQ F45 EM", "SQ HY5 EM", "SQ HYPERMILL EM", "SQ TWISTERMILL EM", # High performance series
                "CR EM", "CR ALUMAZIP EM", # Standard endmills
                "CR V4 EM", "CR V5 EM", "CR V7 EM", "CR AX EM" "CR TAPERMILL EM", "CR F45 EM", "CR HY5 EM", "CR MOLD MILL EM", # High performance series
                "BALL EM", "BALL ALUMAZIP EM", "BALL TAPERMILL EM", # Standard endmills
                "BALL V4 EM", "BALL V5 EM", "BALL AX EM","BALL MOLD MILL EM", # High performance series

                #-- Router Types ---,
                "WOOD ROUTER"
                ]
    em_list = []
    em_list_type_list = ["SQ", "CR", "BALL"]

    for i in tool_types_list:
        if any(i.startswith(et) for et in em_list_type_list) and i.endswith("EM"):
            em_list.append(i)
    # Function to center window 
    # arg: takes a tkinter window
    def center_window(window):
        window.update_idletasks()
        width, height = window.winfo_width(), window.winfo_height()
        x = window.winfo_screenwidth() // 2 - width // 2
        y = window.winfo_screenheight() // 2 - height // 2
        window.geometry(f"{width}x{height}+{x}+{y}")

    # Function to validate user input 
    def validate_input(value):
        accepted_char="0123456789./"
        if value.startswith('.'):
            value = '0' + value
        for char in value:
            if char not in accepted_char:
                return False
        return True
    def on_mass_calc_click():
        global mass_calc
        mass_calc = True
        messagebox.showinfo("Info", "Mass Calculation Mode")
        get_cycle_time()
    def on_calc_click():
        global mass_calc
        mass_calc = False
        get_cycle_time()
    
    def get_mass_calc_xl():
        # Mass Calculation mode
        mass_calc_xl = r"\Reference.xlsx"
        if not os.path.exists(mass_calc_xl):
            messagebox.showerror("Error", "Mass Calc excel not found")
            return
        if mass_calc == True:
            mass_calc_df = pd.read_excel(mass_calc_xl, sheet_name="Test") # Sheet where test data is pulled from
            if mass_calc_df.empty:
                messagebox.showerror("Error", "Mass Calc excel is empty")
                return
            else:
                return mass_calc_df

    # Functions to retrieve user input
    def get_tool_type():
        global message
        message = "Invalid tool type"
        selected_type = type_selection_combobox.get().upper()
        if not selected_type in tool_types_list:
            return 0
        else:
            return selected_type
    def get_tool_dia():
        global message
        message = "Invalid diameter"
        if dia_entry.get() == "":
            return 0
        elif "/" in dia_entry.get():
            try:
                if dia_entry.get().split("/")[0] == "":
                    return 0
                return float(dia_entry.get().split("/")[0]) / float(dia_entry.get().split("/")[1])
            except ZeroDivisionError:
                return 0
        else:
            try:
                return float(dia_entry.get())
            except ValueError:
                return 0
    def get_tool_loc():
        global message
        message = "Invalid length of cut"
        if loc_entry.get() == "":
            return 0
        elif "/" in loc_entry.get():
            try:
                if loc_entry.get().split("/")[0] == "":
                    return 0
                return float(loc_entry.get().split("/")[0]) / float(loc_entry.get().split("/")[1])
            except ZeroDivisionError:
                return 0
        else:
            try:
                return float(loc_entry.get())
            except ValueError:
                return 0
    def get_tool_flute():
        global message
        message = "Invalid number of flutes"
        try:
            if flute_entry.get() == "":
                return 0
            else:
                try:
                    return int(flute_entry.get())
                except ValueError:
                    return 0
        except ValueError:
            return 0

    """Retrieve reference excel based on tool type"""
    def get_reference_xl(tool_type):
        # Read reference excel
        ref_excel = r"\Reference.xlsx" # Reference Excel location
        if not os.path.exists(ref_excel):
            messagebox.showerror("Error", "Reference excel not found")
            return 
        # Retrieve tool data from reference excel
        try:
            ref_df = pd.read_excel(ref_excel, sheet_name=tool_type)
        except ValueError:
            messagebox.showerror("Error", "Tool type not found in reference excel")
            return 
        else:
            return ref_df
    # Function to calculate cycle time
    def calc_cycle_time(diameter, loc, flute_count, tool_type):
        cycle_time = 0.0
        if diameter == 0 or loc == 0 or flute_count == 0 or ref_df is None:
            return
        else:
            # Convert units
            mm_convert_inch = 25.4
            if unit.get() == "mm":
                diameter = diameter / mm_convert_inch
                loc /= mm_convert_inch
            # Filter based on tool diameter
            filtered_df = ref_df[(ref_df["min_diameter"].astype(float) <= diameter) & (ref_df["max_diameter"].astype(float) >= diameter)]
        
            if tool_type in em_list:
                # Static variables from excel
                fluting_feedrate = 0.0
                od_feedrate = 0.0
                end_cycle_time = 0.0
                end_gash_cycle_time = 0.0
                end_split_time = 0.0

                if not filtered_df.empty:
                    if tool_type.endswith("EM"):
                        row_values = filtered_df.iloc[0]
                        fluting_feedrate = row_values["fluting_fr"]
                        od_feedrate = row_values["od_fr"]
                        end_cycle_time = row_values["end_ct"]
                        end_gash_cycle_time = row_values["end_gash_ct"]
                        end_split_time = row_values["end_split_ct"]
                # Check if tool with desired diameter is found within reference excel ranges
                else:
                    if diameter > 0:
                        messagebox.showerror("Error", f"Tool with diameter {diameter} not found in reference excel diameter ranges.")
                    else:
                        messagebox.showerror("Error", "Diameter cannot be 0")
                    return
                
                if mass_calc == False:
                    print(filtered_df)

                """
                    Math for endmill types
                    Ball EM = 1.25x Sqaure Cycle Time
                    CR EM = 1.20x Sqaure Cycle Time
                    High Performance V4 and V5 EM = 1.10x respective Cycle Time
                    Ax EM = 1.15x respective Cycle Time
                """
                # List of possible tool types that will not have 2nd OD angle when dia < 3mm
                dia_cutoff = round(3/mm_convert_inch, 4)
                sec_od_angle = True
                if tool_type in em_list:
                    if diameter < dia_cutoff:
                        sec_od_angle = False
                # Calculate cycle time
                dynamic_variable = 2.5 # Change value to adjust cycle time to be more precise
                inc_percentage = 1 # Change value to adjust percentage increase in cycle time based of tool type

                # Variable for tools with split/notches
                split = False
                
                """ Dictonary for tools with split base on flutes for standard endmills -- """
                split_dict = {"SQ EM": [3,5,6], "BALL EM": [3,4,5,6], "CR EM": [3,5,6], "ALUMAZIP EM": [3]}

                # 2 flute case accounting for passes
                if tool_type in em_list and flute_count == 2:
                    calc_fl_time = (loc/fluting_feedrate)*dynamic_variable*4
                else:
                    calc_fl_time = (loc/fluting_feedrate)*dynamic_variable*flute_count # Fluting Cycle time
                    
                calc_od_time = (loc/od_feedrate)*dynamic_variable*flute_count  # OD Cycle time
                # Adjust cycle time based on 2nd OD angle and tert angle            
                if sec_od_angle and tert_angle.get() == "tert":
                    calc_od_time *= 3.0
                elif sec_od_angle and tert_angle.get() != "tert":
                    calc_od_time *= 2.0

                calc_end_time = ((diameter*.5)/end_cycle_time)*dynamic_variable*flute_count # End Cycle time
                calc_gash_time = ((diameter*.5)/end_gash_cycle_time)*dynamic_variable*flute_count # Gash Cycle time

                # Check if tool type in performance series
                def check_performance_series(tool_type, inc_percentage, split):
                    for ps in perf_series:
                        if ps in tool_type:
                            if ps == "V4" or ps == "V5":
                                inc_percentage += 0.1
                                if tool_type.startswith("SQ") or tool_type.startswith("CR"):
                                    split = False
                            elif ps == "AX":
                                inc_percentage += 0.15
                                split = False
                    return inc_percentage, split
                if tool_type.endswith("EM"):
                    if tool_type.startswith("SQ"):
                        if flute_count in split_dict["SQ EM"]:
                            split = True
                        inc_percentage, split = check_performance_series(tool_type, inc_percentage, split)
                    elif tool_type.startswith("BALL"):
                        inc_percentage = 1.25
                        if flute_count in split_dict["BALL EM"]:
                            split = True
                        inc_percentage, split = check_performance_series(tool_type, inc_percentage, split)
                    elif tool_type.startswith("CR"):
                        inc_percentage = 1.20
                        if flute_count in split_dict["CR EM"]:
                            split = True
                        inc_percentage, split = check_performance_series(tool_type, inc_percentage, split)
                    if "ALUMAZIP" in tool_type:
                        if flute_count in split_dict["ALUMAZIP EM"]:
                            split = True
                        messagebox.showerror("Error", "Alumazip not currently supported for Cycle Time Calculation")
                        return
                if not split:
                    end_split_time = 0.0
                cycle_time = (calc_fl_time + calc_od_time + calc_end_time + calc_gash_time + end_split_time)*inc_percentage
                minutes = int(cycle_time)
                seconds = round((cycle_time - minutes) * 60)
                if minutes > 60:
                    formatted_cycle_time = f"{minutes//60}h {minutes%60}m {seconds}s"
                else:
                    formatted_cycle_time = f"{minutes}m {seconds}s"
                if mass_calc == False:
                    default_cycle_time.set(formatted_cycle_time)
                    print(f"\nDiameter: {diameter}\nLength of Cut: {loc}\nFlute Count: {flute_count}\nCycle Time: {formatted_cycle_time}\n")
                    print(f"Has 2nd OD Angle: {sec_od_angle}")
                    print(f"Has Split: {split}")
                    print(f"Fluting Cycle Time: {calc_fl_time}\nOD Cycle Time: {calc_od_time}\nEnd Cycle Time: {calc_end_time}\nGash Cycle Time: {calc_gash_time}\nSplit Cycle Time: {end_split_time}")
                return formatted_cycle_time, calc_fl_time, calc_od_time, calc_end_time, calc_gash_time, end_split_time
    # Get cycle times
    def get_cycle_time():
        if mass_calc == False:
            tool_type = get_tool_type()
            print(tool_type)
        # Check if tool type is valid
        def check_tool_type(tool_type):
            global ref_df
            if tool_type not in tool_types_list:
                messagebox.showerror("Error", "Tool type not found")
                return
            if tool_type in em_list:
                # For easier use of em_list by multipying by percentages so base feed rates remain unchanged
                ref_df = get_reference_xl("SQ EM")
                #print("Using SQ EM reference data\n")
            else:
                ref_df = get_reference_xl(tool_type)
            if ref_df is None:
                return 0
        # For mass calculations only pulling from excel
        if mass_calc == True:
            index = 0
            # Initialize dataframe   
            result_df = pd.DataFrame(columns=["Tool Type","Part Number","Diameter","Length of Cut","Flute Count", "Cycle Time",
                                        "Fluting Cycle Time", "OD Cycle Time", "End Cycle Time", "Gash Cycle Time", "Split Cycle Time"])
            mass_calc_df = get_mass_calc_xl()
            for index, row in mass_calc_df.iterrows():
                if pd.isna(row["Diameter"]):
                    continue
                part_num = row["Part Number"]
                diameter = row["Diameter"]
                loc = row["Length of Cut"]
                flute_count = row["Flute Count"]
                tool_type = row["Tool Type"]
                if check_tool_type(tool_type) == 0: 
                    return
                result = calc_cycle_time(diameter, loc, flute_count, tool_type)
                if result is None:
                    continue
                result_df.loc[index] = [tool_type ,part_num, diameter, loc, flute_count,
                                        result[0], result[1], result[2], result[3], result[4], result[5]]
            # Store results in excel
            results_path = r"\test_results.csv"
            if not os.path.exists(results_path):
                messagebox.showerror("Error", "Mass Calc excel not found")
                return
            else:
                try:
                    result_df.to_csv(results_path, index=False)
                    messagebox.showinfo("Success", "Mass Calc results stored in test_results.csv")
                    return
                except PermissionError:
                    messagebox.showerror("Error", "Mass Calc results excel is open please close it and try again")
        # For default calculations with user input
        else:
            diameter = get_tool_dia()
            if diameter == 0:
                messagebox.showerror("Error", message)
            loc = get_tool_loc()
            if loc == 0:
                messagebox.showerror("Error", message)
            flute_count = get_tool_flute()
            if flute_count == 0:
                messagebox.showerror("Error", message)
            if diameter == 0 or loc == 0 or flute_count == 0:
                return
            if check_tool_type(tool_type) == 0:
                return
            # Locks flute count for performance series V4 and V5
            for ps in perf_series:
                if ps in tool_type:
                    if ps == "V4":
                        flute_count = 4
                    elif ps == "V5":
                        flute_count = 5
            calc_cycle_time(diameter, loc, flute_count, tool_type)
    # Functions to clear window
    def clear_window():
        default_type.set("SQ EM")
        default_dia.set("0.0000")
        default_loc.set("0.0000")
        default_flute.set("0")
        default_cycle_time.set("0")
        unit.set("in")
        tert_angle.set("0")
    # Main window
    root = tkinter.Tk()
    root.geometry("375x225") # Set window size
    root.title("Cycle Time Calculator")
    root.resizable(False, False)
    root.focus_force()

    # Hidden mass calculation button
    hidden_button_var = tkinter.IntVar()
    hidden_button_var.set(0)
    
    def hidden_mass_calc_btn(event):
        global hidden_mass_calc_btn
        if hidden_button_var.get() == 0:
            hidden_button_var.set(1)
            hidden_mass_calc_btn = ttk.Button(root, text="Mass Calc", command=on_mass_calc_click) # Mass Calc button used for testing many values
            hidden_mass_calc_btn.place(relx=0.15, rely=0.9, anchor="center")
        else:
            hidden_button_var.set(0)
            if hidden_mass_calc_btn is not None:
                hidden_mass_calc_btn.place_forget()
    # Style
    root.configure(bg="lightgray")
    root.option_add("*Font", ("montserrat", 11))
    root.option_add("*TCombobox*Listbox.Font", ("roboto", 9))
    root.option_add("*Entry.Width", 18)

    style = ttk.Style(root)
    widgets_list = ["TLabel", "TButton", "TRadiobutton", "TCombobox", "TEntry", "TCheckbutton"]
    for widget in widgets_list:
        style.configure(widget, background="lightgray")

    """Labels"""
    type_label = ttk.Label(root, text="Tool Type:")
    dia_label = ttk.Label(root, text="Cut Diameter:")
    loc_label = ttk.Label(root, text="Length Of Cut:")
    flute_label = ttk.Label(root, text="Flute Count:")
    cycle_time_label = ttk.Label(root, text="Cycle Time:")
    """Entry Boxs"""
    # Cut Diameter entry box
    default_dia = tkinter.StringVar() 
    default_dia.set("0.0000")
    dia_entry = ttk.Entry(root, justify=tkinter.RIGHT, textvariable=default_dia)
    # Length Of Cut entry box
    default_loc = tkinter.StringVar()
    default_loc.set("0.0000")
    loc_entry = ttk.Entry(root, justify=tkinter.RIGHT, textvariable=default_loc)
    # Flute Count entry box
    default_flute = tkinter.StringVar()
    default_flute.set("0")
    flute_entry = ttk.Entry(root, justify=tkinter.RIGHT, textvariable=default_flute)
    # Cycle Time entry box
    default_cycle_time = tkinter.StringVar()
    default_cycle_time.set("0")
    cycle_time_entry = ttk.Entry(root, justify=tkinter.RIGHT, state="readonly", textvariable=default_cycle_time)

    # Entry validation
    for entry in [dia_entry, flute_entry, loc_entry]:
        entry.config(validate = 'key', validatecommand = (root.register(validate_input), '%P'))
    
    """Combobox"""
    # Tool Type Combobox
    default_type = tkinter.StringVar()
    default_type.set("SQ EM")
    type_selection_combobox = AutocompleteCombobox(root, width=25, completevalues=tool_types_list, textvariable=default_type, font=("roboto", 10))

    # Function to handle focus when user clicks on entry box
    def handle_focus(event):
        if dia_entry.get() == "0.0000":
            dia_entry.delete(0, tkinter.END) # Delete default value
        if loc_entry.get() == "0.0000":
            loc_entry.delete(0, tkinter.END)
        if flute_entry.get() == "0":
            flute_entry.delete(0, tkinter.END)
    dia_entry.bind("<FocusIn>", handle_focus)
    loc_entry.bind("<FocusIn>", handle_focus)
    flute_entry.bind("<FocusIn>", handle_focus)
    dia_entry.focus_set() # Set focus
    
    """Buttons"""
    # Create button
    calc_button = ttk.Button(root, text="Calculate", command=on_calc_click)
    calc_button.bind_all("<Return>", lambda event: on_calc_click()) # Bind Return key to calculate button
    clear_button = ttk.Button(root, text="Clear", command=clear_window)
    clear_button.bind_all("<Delete>", lambda event: clear_window())
    root.bind_all("<Control-Shift-A>", hidden_mass_calc_btn)
    """Radio Button"""  
    unit = tkinter.StringVar()
    tert_angle = tkinter.StringVar()
    # Create Radio Button
    inch_radio = ttk.Radiobutton(root, text="IN", variable=unit, value="in")
    mm_radio = ttk.Radiobutton(root, text="MM", variable=unit, value="mm")
    unit.set("in")

    """Check box"""
    tert_angle_check = ttk.Checkbutton(root, text="TERT", variable=tert_angle, onvalue="tert", offvalue="0")
    
    """Grid Layout"""
    # Place widgets in grid
    type_label.grid(row=0, column=0, padx=5, pady=5)
    dia_label.grid(row=1, column=0, padx=5, pady=5)
    loc_label.grid(row=2, column=0, padx=5, pady=5)
    flute_label.grid(row=3, column=0, padx=5, pady=5,)
    cycle_time_label.grid(row=4, column=0, padx=5, pady=5)

    type_selection_combobox.grid(row=0, column=1)
    dia_entry.grid(row=1, column=1, padx=5, pady=5) # Add entry box to window()
    loc_entry.grid(row=2, column=1, padx=5, pady=5)
    flute_entry.grid(row=3, column=1, padx=5, pady=5)
    cycle_time_entry.grid(row=4, column=1, padx=5, pady=5)

    inch_radio.grid(row=0, column=2, padx=15, pady=5, sticky="w")
    mm_radio.grid(row=1, column=2, padx=15, pady=5, sticky="w")
    tert_angle_check.grid(row=2, column=2, padx=15, pady=5, sticky="w")    
    # Buttons Placement
    calc_button.place(relx=0.63, rely=0.9, anchor="center")
    clear_button.place(relx=0.42, rely=0.9, anchor="center")
    
    # Focus on first entry box and center window
    root.focus_force()
    center_window(root)
    root.mainloop()

if __name__ == "__main__":
    main()
