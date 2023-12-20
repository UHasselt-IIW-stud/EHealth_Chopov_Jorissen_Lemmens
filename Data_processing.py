import influxdb_client
import os
import time
import pandas as pd
import heartpy as hp
import matplotlib.pyplot as plt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import random
import Preferences
import numpy as np
from scipy.signal import butter, lfilter

client = influxdb_client.InfluxDBClient(url=Preferences.url, token=Preferences.token, org=Preferences.org)

query_api = client.query_api()
while(1):
    bucket = Preferences.bucket
    combined_query = f"""from(bucket: "{bucket}")
    |> range(start: -5m)
    |> filter(fn: (r) =>
        (r._measurement == "Stress_Data")
    )
    """

    tables = query_api.query(combined_query, org="EHealth")


    def extract_data_from_records(tables):
        gsr_data = []
        x_acc_data = []
        y_acc_data = []
        z_acc_data = []
        bpm = []
        sp02 = []
        height = 0
        weight = 0
        age = 0

        for table in tables:
            for record in table.records:
                # Extracting time, field, and value from the record
                measurement = record.get_measurement()
                field = record.get_field()
                value = record.get_value()
                time = record.get_time()
                if field == "gsr_value":
                    gsr_data.append((time, measurement, value))
                elif field == "acceleration_X":
                    x_acc_data.append((time, measurement, value))
                elif field == "acceleration_Y":
                    y_acc_data.append((time, measurement, value))
                elif field == "acceleration_Z":
                    z_acc_data.append((time, measurement, value))
                elif field == "bpm":
                    bpm.append((time, measurement, value))
                elif field == "sp02":
                    sp02.append((time, measurement, value))
                elif field == "height":
                    height = value
                elif field == "weight":
                    weight = value           
                elif field == "age":
                    age = value

        return gsr_data, x_acc_data, y_acc_data, z_acc_data, bpm, sp02, height, age, weight

    # Function to convert data to DataFrames and make values numeric
    def convert_to_numeric_and_create_df(tables):
        gsr_data, x_acc_data, y_acc_data, z_acc_data, bpm, sp02, height, age, weight = extract_data_from_records(tables)

        # Convert data to DataFrames
        df_gsr = pd.DataFrame(gsr_data, columns=["Time", "Measurement", "Value"])
        df_acc_x = pd.DataFrame(x_acc_data, columns=["Time", "Measurement", "Value"])
        df_acc_y = pd.DataFrame(y_acc_data, columns=["Time", "Measurement", "Value"])
        df_acc_z = pd.DataFrame(z_acc_data, columns=["Time", "Measurement", "Value"])
        bpm = pd.DataFrame(bpm, columns=["Time", "Measurement", "Value"])  # DataFrame for rValue
        sp02 = pd.DataFrame(sp02, columns=["Time", "Measurement", "Value"])  # DataFrame for irValue

        # Convert "Value" column to numeric in each DataFrame
        df_gsr["Value"] = pd.to_numeric(df_gsr["Value"], errors="coerce")
        df_acc_x["Value"] = pd.to_numeric(df_acc_x["Value"], errors="coerce")
        df_acc_y["Value"] = pd.to_numeric(df_acc_y["Value"], errors="coerce")
        df_acc_z["Value"] = pd.to_numeric(df_acc_z["Value"], errors="coerce")
        bpm["Value"] = pd.to_numeric(bpm["Value"], errors="coerce")
        sp02["Value"] = pd.to_numeric(sp02["Value"], errors="coerce")

        df_gsr["Value"] = np.nan_to_num(df_gsr["Value"])
        df_acc_x["Value"] = np.nan_to_num(df_acc_x["Value"])
        df_acc_y["Value"] = np.nan_to_num(df_acc_y["Value"])
        df_acc_z["Value"] = np.nan_to_num(df_acc_z["Value"])
        bpm["Value"] = np.nan_to_num(bpm["Value"])
        sp02["Value"] = np.nan_to_num(sp02["Value"])

        return df_gsr, df_acc_x, df_acc_y, df_acc_z, bpm, sp02, height, age, weight


    def filtered_bpm_values(bpm):
        filtered_bpm = bpm.copy()
        while True:
            # Store the length of the previous 'bpm' DataFrame
            prev_length = len(filtered_bpm)

            # Calculate differences between consecutive filtered_bpm values
            filtered_bpm_diff = np.diff(filtered_bpm['Value'])

            # Find indices where the drop is greater than 20 filtered_bpm or rise is greater than 20 filtered_bpm
            indices_of_drop = np.where(filtered_bpm_diff < -25)[0]
            indices_of_rise = np.where(filtered_bpm_diff > 25)[0]

            # Combine the indices of drops and rises
            indices_to_remove = np.concatenate((indices_of_drop, indices_of_rise)) + 1

            # Ensure the indices to remove are within the DataFrame index range
            indices_to_remove = indices_to_remove[indices_to_remove < len(filtered_bpm)]

            # Check if any indices need to be removed
            if len(indices_to_remove) > 0:
                # Check if the indices to remove actually exist in the DataFrame index
                indices_to_remove = indices_to_remove[indices_to_remove < len(filtered_bpm.index)]

                # Remove instances of drops or rises from the 'filtered_bpm' DataFrame
                filtered_bpm = filtered_bpm.drop(filtered_bpm.index[indices_to_remove])
            else:
                break  # If no drops or rises are found, exit the loop

            # Check if no elements were removed in this iteration
            if len(filtered_bpm) == prev_length:
                break  # If no elements were removed, exit the loop

        filtered_bpm = filtered_bpm[(filtered_bpm['Value'] >= 40) & (filtered_bpm['Value'] <= 180)]

        return filtered_bpm

    '''
    def calibrated_gsr(gsr_data):
        calibrated_gsr_data = gsr_data.copy()
        # Define calibration range
        actual_min = 496
        actual_max = 4095
        new_min = 0
        new_max = 4095

        # Function to calibrate GSR values
        def calibrate_gsr(actual_value, actual_min, actual_max, new_min, new_max):
            mapped_value = ((actual_value - actual_min) / (actual_max - actual_min)) * (new_max - new_min) + new_min
            return mapped_value

        # Calibrate each GSR value in the dataset
        calibrated_gsr_data['Value'] = [calibrate_gsr(value, actual_min, actual_max, new_min, new_max) for value in
                                        gsr_data["Value"]]

        return calibrated_gsr_data
    '''

    def calibrated_z_acc_data(z_acc_data):
        # Adding 10 to every value
        z_acc_data['Value'] = z_acc_data['Value'].add(10)

        return z_acc_data

    def is_in_target_heart_rate(age, heart_rate):
        # Dictionary containing age-specific target heart rate zones
        target_zones = {
            (10, 20): (100, 170),
            (20, 30): (85, 162), '''ter demonstratie harstalg waarden aangepast (normale range tussen 95:162)'''
            (30, 35): (93, 157),
            (35, 40): (90, 153),
            (40, 45): (88, 149),
            (45, 50): (85, 145),
            (50, 55): (83, 140),
            (55, 60): (80, 136),
            (60, 65): (78, 132),
            (65, 70): (75, 128)
        }
        
        # Check if the provided age range is in the dictionary
        for age_range, rate_range in target_zones.items():
            if age_range[0] <= age < age_range[1]:
                min_rate, max_rate = rate_range
                
                # Check if the heart rate falls within the target zone
                if min_rate <= heart_rate <= max_rate:
                    return True  # Heart rate is within the target zone
                else:
                    return False  # Heart rate is outside the target zone
        
        return False  # Age range not found in the provided dictionary

    def calculate_stress_level(sp02_data, bpm_data, gsr_data, age):
        stress_level = 0
        stress_levels = []

        for i in range(min(len(sp02_data), len(bpm_data), len(gsr_data))):
            # Check if index is within range
            if i - 1 >= 0:
                # Check conditions and update stress level
                if ((gsr_data[i] > gsr_data[i - 1]) and
                        (bpm_data[i] > bpm_data[i-1]) and
                        (sp02_data[i] <= sp02_data[i - 1])):
                    stress_level += 1       
                    print("Stress Level:", stress_level)
                elif ((gsr_data[i] > gsr_data[i - 1]) and
                        (is_in_target_heart_rate(age, bpm_data[i])) and
                        (sp02_data[i] <= sp02_data[i - 1])):
                    stress_level += 1
                    print("Stress Level:", stress_level)
                elif ((gsr_data[i] < gsr_data[i - 1]) and
                        (is_in_target_heart_rate(age, bpm_data[i])) and
                        (sp02_data[i] <= sp02_data[i - 1])):
                    stress_level += 1
                    print("Stress Level:", stress_level)
                elif ((gsr_data[i] < gsr_data[i - 1]) and
                        (not is_in_target_heart_rate(age, bpm_data[i])) and
                        (sp02_data[i] > sp02_data[i - 1])):
                    stress_level = max(0, stress_level - 1)
                elif ((gsr_data[i] < gsr_data[i - 1]) and
                        (bpm_data[i] < bpm_data[i-1]) and
                        (sp02_data[i] > sp02_data[i - 1])):
                    stress_level = max(0, stress_level - 1)            
                    print("Stress Level:", stress_level)
                elif ((gsr_data[i] > gsr_data[i - 1]) and
                        (bpm_data[i] > bpm_data[i-1]) and
                        (sp02_data[i] > sp02_data[i - 1])):
                    stress_level = max(0, stress_level - 1)            
                    print("Stress Level:", stress_level)
                else:
                    stress_level = max(0, stress_level - 1)

            stress_levels.append(stress_level)
        stress_levels = pd.DataFrame(stress_levels, columns=['Value'])
        stress_levels['Value'] = np.nan_to_num(stress_levels['Value'])

        # Print the calculated stress levels
        print("Stress Levels:", stress_levels)
        return stress_levels


    def generate_stressed_bpm_data(size):
        # Simulating a higher heart rate indicating stress (e.g., 120 to 150 BPM)
        return np.random.randint(120, 151, size=size)

    # Generating a sample array of BPM data (e.g., 100 data points)

    def plot_all():
        print("\nsp02:")
        print(sp02['Value'].mean())

        print("\nbpm:")
        print(filtered_bpm_data['Value'].mean())

        # Create a figure with multiple subplots
        fig, axs = plt.subplots(nrows=5, ncols=1, figsize=(20, 24))
        
        # Plot GSR data
        axs[0].plot(gsr_data['Value'], color='orange', label='raw')
        #axs[0].plot(calibrated_gsr_data['Value'], color='blue', label='calibrated')
        #axs[0].plot(calibrated_gsr_data['Value'].rolling(window=20).mean(), color='green', label='rolling mean')
        axs[0].legend()
        axs[0].grid()
        axs[0].set_title('GSR Data')

        # Plot BPM data
        # axs[1].plot(bpm['Value'], color='black', label = 'raw')
        # axs[1].plot(filtered_bpm['Value'], color='red', label = 'filtered')
        axs[1].plot(filtered_bpm_data["Value"].rolling(window=20).mean(), color='green', label='rolling mean')

        axs[1].legend()
        axs[1].grid()
        axs[1].set_title('BPM Data')

        # Plot SpO2 data
        #axs[2].plot(sp02['Value'], color='black', label='raw')
        axs[2].plot(sp02['Value'].rolling(window=20).mean(), color='blue', label='rolling mean')
        axs[2].legend()
        axs[2].grid()
        axs[2].set_title('SpO2 Data')

        # Plot x-axis Movement data
        axs[3].plot(x_acc_data['Value'].rolling(window=20).mean(), label='x-movement')
        # Plot y-axis Movement data
        axs[3].plot(y_acc_data['Value'].rolling(window=20).mean(), label='y-movement')
        # Plot z-axis Movement data
        axs[3].plot(z_acc_data['Value'].rolling(window=20).mean(), label='z-movement')
        axs[3].legend()
        axs[3].grid()
        axs[3].set_title('Movement')

        axs[4].plot(stress_levels['Value'], color='black', label='stress')
        axs[4].legend()
        axs[4].grid()
        axs[4].set_title('stress level')

        # Adjust layout and display
        plt.tight_layout(pad=6.0)
        plt.show()
        return 0

    gsr_data, x_acc_data, y_acc_data, z_acc_data, bpm, sp02, height, age, weigth = convert_to_numeric_and_create_df(tables)
    filtered_bpm_data = filtered_bpm_values(bpm)
    data = generate_stressed_bpm_data(300)
    #calibrated_gsr_data = calibrated_gsr(gsr_data)
    z_acc_data = calibrated_z_acc_data(z_acc_data)
    stress_levels = calculate_stress_level(sp02['Value'].tolist(), data,
                                            gsr_data["Value"].tolist(), age)
    print("\n height: " + str(stress_levels.mean()))
    #plot_all()


    client = influxdb_client.InfluxDBClient(url=Preferences.url, token=Preferences.token, org=Preferences.org)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    point = (
        Point("Stress_Data")  # Use a unique measurement name for each segment
        .field("Average_stress_level", stress_levels['Value'].mean())
    )
    # Write the data point to InfluxDB
    write_api.write(bucket = bucket, org="EHealth", record=point)
    time.sleep(60*5)
