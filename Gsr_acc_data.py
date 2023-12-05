# vragen voor thijs: (Ge kunt eerst zelf over een paar vragen nadenken voordat ge ze stelt tho kan zijn dat mn vragen retarded zijn)
    # moet ge met platformio alleen maar raw sensor data naar de influx sturen? of mag men al bewerkingen doen in platformio? (mss is het doorsturen van data dan trager?)
    # Is het de bedoeling om bij de final product ervoor te zorgen dat we onze laptop totaal niet meer moeten gebruiken? dus zonder het opstarten van containers? (lijkt me onlogisch)
    # Vraag of ze van die electrode skin tape dingen kunnen geven / als ze dat hebben.
    # kunnen we de verwerkte data ook via een website (html) displayen ipv een app?
    # of we zo een batterij om aan het bordje te hangen zouden kunnen krijgen
    # hoe belangrijk is het gebruik van SPI's? we zouden de gsr sensor op een miso kunnen zetten maar heeft dat veel nut als het maar 1 sensor is die op deze lijn staat? (mss staat antwoord in de slides moet ge eens nakijken)
    # kunnen we verschillende sample rates gebruiken op 1 ESP bordje? Omdat een goeie sample rate voor gsr tussen 1-10 Hz is en die van ppg tussen 20 - 50 Hz
    
    # ...

# WAT ER IN DE CODE GEBEURT
# Code is heel gelijkaardig aan de code van de opdracht met ECG data
# In deze code halen we nu gewoon alle waardes uit de influx, dus: Accelerometer (x,y,z - beweging), ppg meting, gsr meting)
# elke soort data zetten we in een aparte dataframe
# waardes die we willen gebruiken zetten we om naar numeric (kan zijn dat da voor de value niet moet, zou ge eens kunnen proberen ofdat da zo is)
# daarna berekenen we maar snel het gemiddelde om te kijken of we effectief iets kunnen doen met die data
# ...

# WAT TE DOEN
# probeer gsr en ppg data te verwerken
# kijk welke waarden men uit gsr en ppg data kan halen waarmee we de link met stress kunnen leggen
# als ge gewoon al weet welke waardes we moeten meten (gelijk oxygen lvl, hartslag, bloodflow) kunt  ge ze daarna filteren en printen
# dan zitten we al ver
# ge zou de snelheid uit een accelerometer kunnen bepalen maar dat is al moeilijker denk ik (als het zelfs gaat om snelheid te berekenen)
# het zou kunnen zijn dat ge in uw main.cpp uw setup van uw ppg signaal moet aanpassen naarmate welke metingen ge wilt gaan doen (ale dat gok ik toch)

# ALS WIFI/INFLUX NIET WERKT
# in uw main.cpp file line 65 in comment zetten en dan de code eens proberen te runnen
# laptop met zelfde wifi als bordje verbinden om met influx te connecten
# docker opstarten om met influx te connecten

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
