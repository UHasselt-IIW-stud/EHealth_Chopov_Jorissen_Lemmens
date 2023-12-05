import influxdb_client
import os
import time
import pandas as pd
import matplotlib.pyplot as plt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
import random
import Preferences
import numpy as np

client = influxdb_client.InfluxDBClient(url=Preferences.url, token=Preferences.token, org=Preferences.org)

sample_rate = 10
bucket = "Raw_Data_ecg_bloeddruk"

while(1):

    query_api = client.query_api()

    combined_query = """from(bucket: "Raw_Data_ecg_bloeddruk")
    |> range(start: -1m)
    |> filter(fn: (r) =>
        (r._measurement == "GSR_Data") or
        (r._measurement == "ACC_Data") or
        (r._measurement == "PPG_Data")
    )
    """

    tables = query_api.query(combined_query, org="EHealth")

    gsr_data = []
    x_acc_data = []
    y_acc_data = []
    z_acc_data = []
    ppg_data = []

    for table in tables:
        for record in table.records:
            # Extracting time, field, and value from the record
            if record.get_measurement() == "GSR_Data":
                gsr_data.append((record.get_time(), record.get_field(), record.get_value()))
            elif record.get_measurement() == "ACC_Data" and record.get_field() == "acceleration_X":
                x_acc_data.append((record.get_time(), record.get_field(), record.get_value()))
            elif record.get_measurement() == "ACC_Data" and record.get_field() == "acceleration_Y":
                y_acc_data.append((record.get_time(), record.get_field(), record.get_value()))
            elif record.get_measurement() == "ACC_Data" and record.get_field() == "acceleration_Z":
                z_acc_data.append((record.get_time(), record.get_field(), record.get_value()))
            elif record.get_measurement() == "PPG_Data":
                ppg_data.append((record.get_time(), record.get_field(), record.get_value()))

    df_gsr = pd.DataFrame(gsr_data, columns=["Time", "Measurement", "Value"])
    df_acc_x = pd.DataFrame(x_acc_data, columns=["Time", "Measurement", "Value"])
    df_acc_y = pd.DataFrame(y_acc_data, columns=["Time", "Measurement", "Value"])
    df_acc_z = pd.DataFrame(z_acc_data, columns=["Time", "Measurement", "Value"])
    df_ppg = pd.DataFrame(ppg_data, columns=["Time", "Measurement", "Value"])

    df_gsr['Value'] = pd.to_numeric(df_gsr['Value'], errors='coerce')
    df_gsr['Time'] = pd.to_numeric(df_gsr['Time'], errors='coerce')
    data_acc_x = pd.to_numeric(df_acc_x['Value'], errors='coerce')
    data_acc_y = pd.to_numeric(df_acc_y['Value'], errors='coerce')
    data_acc_z = pd.to_numeric(df_acc_z['Value'], errors='coerce')
    df_ppg['Value'] = pd.to_numeric(df_ppg['Value'], errors='coerce')
    df_ppg['Time'] = pd.to_numeric(df_ppg['Time'], errors='coerce')


    mean_value_ppg = df_ppg['Value'].mean()
    mean_value_gsr = df_gsr['Value'].mean()
    median_value = df_gsr['Value'].median()
    min_value = df_gsr['Value'].min()
    max_value = df_gsr['Value'].max()
    std_deviation = df_gsr['Value'].std()

    print("Mean gsr:", mean_value_gsr)
    print("Mean ppg:", mean_value_ppg)
    
    '''
    print("Median:", median_value)
    print("Min:", min_value)
    print("Max:", max_value)
    print("Standard Deviation:", std_deviation)

    plt.figure(figsize=(12, 4))
    plt.plot(df_gsr['Time'], df_gsr['Value'])
    plt.xlabel('Time')
    plt.ylabel('GSR Value')
    plt.title('GSR Data Over Time')

    rolling_mean = df_gsr['Value'].rolling(window=10).mean()  # Adjust window size as needed
    plt.plot(df_gsr['Time'], rolling_mean, label='Rolling Mean')
    plt.legend()
    plt.show()
    '''
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
    time.sleep(60)