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

sample_rate = 100
bucket = "Raw_Data_ecg_bloeddruk"


query_api = client.query_api()

combined_query = """from(bucket: "Raw_Data_ecg_bloeddruk")
|> range(start: -30m)
|> filter(fn: (r) =>
    (r._measurement == "GSR_Data") or
    (r._measurement == "ACC_Data") or
    (r._measurement == "PPG_Data")
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

    for table in tables:
        for record in table.records:
            # Extracting time, field, and value from the record
            measurement = record.get_measurement()
            field = record.get_field()
            value = record.get_value()
            time = record.get_time()

            if measurement == "GSR_Data":
                gsr_data.append((time, measurement, value))
            elif measurement == "ACC_Data" and field == "acceleration_X":
                x_acc_data.append((time, measurement, value))
            elif measurement == "ACC_Data" and field == "acceleration_Y":
                y_acc_data.append((time, measurement, value))
            elif measurement == "ACC_Data" and field == "acceleration_Z":
                z_acc_data.append((time, measurement, value))
            elif measurement == "PPG_Data" and field == "bpm":
                bpm.append((time, measurement, value))
            elif measurement == "PPG_Data" and field == "sp02":
                sp02.append((time, measurement, value))

    return gsr_data, x_acc_data, y_acc_data, z_acc_data, bpm, sp02

# Function to convert data to DataFrames and make values numeric
def convert_to_numeric_and_create_df(tables):
    gsr_data, x_acc_data, y_acc_data, z_acc_data, bpm, sp02 = extract_data_from_records(tables)
    
    # Convert data to DataFrames
    df_gsr = pd.DataFrame(gsr_data, columns=["Time", "Measurement", "Value"])
    df_acc_x = pd.DataFrame(x_acc_data, columns=["Time", "Measurement", "Value"])
    df_acc_y = pd.DataFrame(y_acc_data, columns=["Time", "Measurement", "Value"])
    df_acc_z = pd.DataFrame(z_acc_data, columns=["Time", "Measurement", "Value"])
    bpm = pd.DataFrame(bpm, columns=["Time", "Measurement", "Value"])  # DataFrame for rValue
    sp02 = pd.DataFrame(sp02, columns=["Time", "Measurement", "Value"])  # DataFrame for irValue

    # Print the created DataFrames
    print("DataFrame for GSR data:")
    print(df_gsr)

    print("\nDataFrame for X-axis Movement data:")
    print(df_acc_x)

    print("\nDataFrame for Y-axis Movement data:")
    print(df_acc_y)

    print("\nDataFrame for Z-axis Movement data:")
    print(df_acc_z)

    print("\nDataFrame for BPM data:")
    print(bpm)

    print("\nDataFrame for SpO2 data:")
    print(sp02)
    
    # Convert "Value" column to numeric in each DataFrame
    df_gsr["Value"] = pd.to_numeric(df_gsr["Value"], errors="coerce")
    df_acc_x["Value"] = pd.to_numeric(df_acc_x["Value"], errors="coerce")
    df_acc_y["Value"] = pd.to_numeric(df_acc_y["Value"], errors="coerce")
    df_acc_z["Value"] = pd.to_numeric(df_acc_z["Value"], errors="coerce")
    bpm["Value"] = pd.to_numeric(bpm["Value"], errors="coerce")
    sp02["Value"] = pd.to_numeric(sp02["Value"], errors="coerce")

    return df_gsr, df_acc_x, df_acc_y, df_acc_z, bpm, sp02

# Example usage
# Assuming 'tables' variable contains the data

# df_gsr, df_acc_x, df_acc_y, df_acc_z, df_ppg = convert_to_numeric_and_create_df(tables)
gsr_data, x_acc_data, y_acc_data, z_acc_data, bpm, sp02 = convert_to_numeric_and_create_df(tables)
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

    print("\nsp02:")
    print(sp02['Value'].mean())

    print("\nbpm:")
    print(filtered_bpm['Value'].mean())

filtered_bpm = filtered_bpm[(filtered_bpm['Value'] >= 40) & (filtered_bpm['Value'] <= 180)]

print("\nsp02:")
print(sp02['Value'].mean())

print("\nbpm:")
print(filtered_bpm['Value'].mean())

rolling_mean = gsr_data['Value'].rolling(window=10).mean()  # Adjust window size as needed
# Create a figure with multiple subplots
fig, axs = plt.subplots(nrows=4, ncols=1, figsize=(16, 24))

# Plot GSR data
axs[0].plot(gsr_data['Value'], color='orange')
axs[0].legend()
axs[0].grid()
axs[0].set_title('GSR Data')

# Plot BPM data
axs[1].plot(filtered_bpm['Value'].rolling(window=50).mean(), color='red', label = 'rolling mean')
axs[1].plot(bpm['Value'], color='black', label = 'raw')
axs[1].plot(filtered_bpm['Value'], color='green', label = 'filtered')
axs[1].legend()
axs[1].grid()
axs[1].set_title('BPM Data')

# Plot SpO2 data
axs[2].plot(sp02['Value'].rolling(window=50).mean(),color='blue', label = 'rolling mean')
axs[2].plot(sp02['Value'], color='black',label = 'raw')
axs[2].legend()
axs[2].grid()
axs[2].set_title('SpO2 Data')

# Plot x-axis Movement data
axs[3].plot(x_acc_data['Value'], label='x-movement')
# Plot z-axis Movement data
axs[3].plot(z_acc_data['Value'], label='z-movement')
# Plot y-axis Movement data
axs[3].plot(y_acc_data['Value'], label='y-movement')
axs[3].legend()
axs[3].grid()

# Adjust layout and display
plt.tight_layout(pad=5.0)
plt.show()

'''
client = influxdb_client.InfluxDBClient(url=Preferences.url, token=Preferences.token, org=Preferences.org)
bucket = "Clear_Data_ecg_bloeddruk"
write_api = client.write_api(write_options=SYNCHRONOUS)
random_patient_number = random.randint(1,100)
point = (

)
# Write the data point to InfluxDB
write_api.write(bucket=bucket, org="EHealth", record=point)
'''