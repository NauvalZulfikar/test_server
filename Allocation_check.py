import pandas as pd
import time
import xlwings as xw
from datetime import datetime, timedelta
import plotly.express as px
from IPython.display import display, clear_output
import streamlit as st
import plotly.graph_objects as go
import altair as alt
import subprocess
import openpyxl
import sqlalchemy
import urllib.parse
from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, DateTime
import psycopg2
from psycopg2 import sql
from psycopg2.extras import execute_values
import sys
import queue
from multiprocessing import Queue, current_process, get_context
import argparse
import dash_table

output_queue = queue.Queue()

# Initialize machine status dictionary
machine_status = {}
O1 = 0

interrupted = False

def update_database(components_df, connection):
    # Assuming 'components' is the name of your SQL table
    table_name = 'prodet'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'  # Correct IP address or hostname
    db_port = '5432'  # Assuming default PostgreSQL port
    db_name = 'ProductDetails'
    # Encode username and password for safe URL inclusion
    encoded_username = urllib.parse.quote_plus(db_username)
    encoded_password = urllib.parse.quote_plus(db_password)

    # Construct the connection URL
    db_url = f'postgresql+psycopg2://{encoded_username}:{encoded_password}@{db_host}:{db_port}/{db_name}'

    try:
        engine = create_engine(db_url)
        connection = engine.connect()
        print("Connection successful!")
    except Exception as e:
        print(f"Connection failed: {e}")
    # Append data to the table in PostgreSQL
    components_df.to_sql(table_name, engine, if_exists='replace', index=False)

def update_runtime(run_time):
    # Establish the database connection
        conn = psycopg2.connect(
            dbname="ProductDetails",
            user="PUser12",
            password="PSQL@123",
            host="localhost",
            port="5432"
        )
        update_query = '''UPDATE public."RunTime" SET "Run_time" = %s;'''
        with conn.cursor() as cursor:
            cursor.execute(update_query,(run_time,))
            conn.commit()
        conn.close()


def update_excel(components_df, connection):
    # Assuming that update_database function is responsible for the SQL update
    update_database(components_df, connection)


def fetch_data():
    try:
        # Establish the database connection
        conn = psycopg2.connect(
            dbname="ProductDetails",
            user="PUser12",
            password="PSQL@123",
            host="localhost",
            port="5432"
        )
        cursor = conn.cursor()
        
        # Fetch data from the 'Addln' table
        query_addln = sql.SQL('SELECT * FROM {schema}.{table} ORDER BY {order_col}').format(
            schema=sql.Identifier('public'),
            table=sql.Identifier('Addln'),
            order_col=sql.Identifier('UniqueID')
        )
        addln_df = pd.read_sql(query_addln.as_string(conn), conn)
        
        if not addln_df.empty:
            # Insert data from 'Addln' to 'prodet'
            tuples = [tuple(x) for x in addln_df.to_numpy()]
            cols = ','.join(list(addln_df.columns))
            query = sql.SQL('INSERT INTO {schema}.{table} ({cols}) VALUES %s').format(
                schema=sql.Identifier('public'),
                table=sql.Identifier('prodet'),
                cols=sql.SQL(',').join(map(sql.Identifier, addln_df.columns))
            )
            execute_values(cursor, query.as_string(conn), tuples)
            conn.commit()
            print("Data from Addln table appended to prodet table.")
            
            # Delete data from 'Addln' table
            cursor.execute(sql.SQL('TRUNCATE TABLE {schema}.{table}').format(
                schema=sql.Identifier('public'),
                table=sql.Identifier('Addln')
            ))
            conn.commit()
            print("Addln table data deleted.")
        
        # Fetch updated data from the 'prodet' table
        query_prodet = sql.SQL('SELECT * FROM {schema}.{table} ORDER BY {order_col}').format(
            schema=sql.Identifier('public'),
            table=sql.Identifier('prodet'),
            order_col=sql.Identifier('UniqueID')
        )

        prodet_df = pd.read_sql(query_prodet.as_string(conn), conn)
        #print(prodet_df)
        cursor.close()
        conn.close()
        
        return prodet_df

    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()


def calculate_remaining_time(product_name, components_df):
    remaining_components = components_df[(components_df['Product Name'] == product_name) & 
                                         (components_df['Status'] != 'Completed')]
    total_remaining_time = 0
    for index, row in remaining_components.iterrows():
        run_time_per_1000 = row['Run Time (min/1000)']
        quantity = row['Quantity Required']
        cycle_time = (run_time_per_1000 * quantity) / 1000
        total_remaining_time += cycle_time * 60  # Convert to seconds
    return total_remaining_time

def allocate_machines(outsource_df, components_df, machines_df, Similarity_df,connection,input_data):
    global O1
    frststep=0
    machine_status = {machine: 0 for machine in machines_df['Machines'].tolist()}
    last_processed = {machine: (None, None, None, None) for machine in machines_df['Machines'].tolist()}  # To store last processed (component, machine, operation)
    #Outcycle_time = 20
    CurrentOutSrcPN = ''
    #simulated_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)  # Start time at 9 am
    simulated_time = datetime.now()
    ReadyTime = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)  # Start time at 9 am
    animation_data = []
    global interrupted
    #print(components_df)

    if input_data == "Start":

        # Initialize O1 and CurrentPN
        O1 = 0
        CurrentPN = None

        # Check for any 'Outsrc' component that is 'InProgress'
        in_progress_outsrc = components_df[(components_df['Status'] == 'InProgress') & (components_df['Process Type'] == 'Outsource')]

        print(in_progress_outsrc)
        # If there are any such components, set O1 and CurrentPN
        if not in_progress_outsrc.empty:
            O1 = 1
            CurrentPN = in_progress_outsrc.iloc[0]['Product Name']


    while True:
        if interrupted:
            break

        #if simulated_time.hour == 17:
         #   print("Stopping the bot as it is 17:00")
          #  break
        
        #if 12 <= simulated_time.hour < 13:
         #   print("Pausing the bot for lunch break (12:00 PM to 1:00 PM)")
          #  simulated_time += timedelta(hours=1)
           # continue
        
        components_df=fetch_data()  
        #print(components_df)
        remaining_components = components_df[components_df['Status'] != 'Completed']
        #print(remaining_components)
        if remaining_components.empty:
            break

        for index, row in remaining_components.iterrows():
            #print(f"{index}Index")
            component = row['Components']
            cycle_time_r = row['Run Time (min/1000)']
            Qnty = row['Quantity Required']
            cycle_time = (cycle_time_r * Qnty) / 1000  # in minutes
            cycle_time_seconds = cycle_time * 60  # convert cycle_time to seconds
            machine_number = row['Machine Number']
            status = row['Status']
            ProductNames = row['Product Name']
            ProcessType = row['Process Type']
            PromisedDeliveryDate = row['Promised Delivery Date']
            operation = row['Operation']
            Outcycle_time = row['Run Time (min/1000)']
            CurrentTimeStrt=datetime.now()
           
            similarity_rows = Similarity_df.loc[Similarity_df['Machine'] == machine_number, 'Status']
            similarity_status = similarity_rows.values[0] if not similarity_rows.empty else 0

            if O1 == 1 and CurrentOutSrcPN == ProductNames:
                continue

            if (O1 == 1 and ProductNames == CurrentPN) or (status == "InProgress" and ProcessType=="Outsource"):
                CurrIndex = index
                current_Ptime = simulated_time
                #for ind, ro in outsource_df.iterrows():
                 #   ProdName=ro['Product']
                  #  CompoName=ro['Components']
                   # if ProdName==ProductNames:
                    #    Outcycle_time=ro['Outsource Time']
                     #   break
                        
                print(Outcycle_time)
                
                OutsrcSrt_Time = pd.to_datetime(components_df.loc[CurrIndex, 'Start Time'], errors='coerce')
                print(OutsrcSrt_Time)
                if OutsrcSrt_Time!=None:

                    #print(f"{current_Ptime}, {OutsrcSrt_Time}, {Outcycle_time}")
                    #print(f"{CurrIndex} CurrentPtime(Sim) diff OutsrcTime")
                    l=current_Ptime-OutsrcSrt_Time
                    d=l.total_seconds()
                    #print(f"{d}, {CurrIndex} CurrentPtime(Sim) diff OutsrcTime")
               
                    if l.total_seconds() >= Outcycle_time:
                        #print(f"{current_Ptime}, {OutsrcSrt_Time}, {Outcycle_time}")
                        O1 = 0
                        O1End_time = current_Ptime
                        components_df.loc[CurrIndex, 'End Time'] = O1End_time.strftime("%H:%M:%S")  # Update only time
                        components_df.loc[CurrIndex, 'Status'] = 'Completed'
                        
                        #stop_clock(machine_number)
                        
                        remaining_time = calculate_remaining_time(ProductNames, components_df)
                        time_to_deadline = (PromisedDeliveryDate - simulated_time).total_seconds()
                        
                        #print(remaining_time)
                        #print(time_to_deadline)
                        # Convert time_to_deadline from seconds to H:M:S
                        total_seconds = int(time_to_deadline)
                        hours, remainder = divmod(total_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        deadline_time_str = f"{hours:02}:{minutes:02}:{seconds:02}"

                        # Convert remaining_time from seconds to H:M:S
                        remaining_total_seconds = int(remaining_time) 
                        remaining_hours, remaining_remainder = divmod(remaining_total_seconds, 3600)
                        remaining_minutes, remaining_seconds = divmod(remaining_remainder, 60)
                        remaining_time_str = f"{remaining_hours:02}:{remaining_minutes:02}:{remaining_seconds:02}"
                        #print(remaining_time_str)
                        #print(deadline_time_str)
                        #components_df.loc[CurrIndex, 'Deadline Time'] = deadline_time_str  # Update only time
                        #components_df.loc[CurrIndex, 'Remaining Time'] = remaining_time_str  # Update only time
                        #remaining_time=2
                        #time_to_deadline=1
                        if remaining_time > time_to_deadline:
                            remaining_components = components_df[components_df['Status'] != 'Completed']
                            remaining_components = remaining_components[remaining_components['Product Name'] == ProductNames]
                            #print(remaining_components)

                        else:
                            remaining_components = components_df[components_df['Status'] != 'Completed']

                        CurrentOutSrcPN = ''
                        CurrIndex = ''
                update_excel(components_df,connection)
                if ProductNames == CurrentPN:
                    CurrentTimEnd=datetime.now()
                    diff= CurrentTimEnd-CurrentTimeStrt
                    simulated_time = simulated_time + diff
                    continue

            if status == 'InProgress' and ProcessType == 'Outsource':
                CurrentOutSrcPN = ProductNames
                update_excel(components_df,connection)
                CurrentTimEnd=datetime.now()
                diff= CurrentTimEnd-CurrentTimeStrt
                simulated_time = simulated_time + diff
                continue

            if status != 'Completed':
                if ProcessType == 'Outsource':
                    O1 = 1
                    OutsrcSrt_Time = simulated_time
                    components_df.loc[index, 'Start Time'] = OutsrcSrt_Time.strftime("%H:%M:%S")  # Update only time
                    components_df.loc[index, 'Status'] = 'InProgress'
                    CurrIndex = index
                    CurrentPN = ProductNames
                    update_excel(components_df,connection)
                    continue
                else:
                    if machine_status[machine_number] == 0:
                        # Calculate wait time and update it
                        wait_time = simulated_time - ReadyTime
                        #print(wait_time)
                        wait_time_str = f"{wait_time.seconds // 3600:02}:{(wait_time.seconds // 60) % 60:02}:{wait_time.seconds % 60:02}"
                        components_df.loc[index, 'Wait Time'] = wait_time_str  # Update only time
                        
                        machine_status[machine_number] = 1
                        start_time = simulated_time
                        components_df.loc[index, 'Start Time'] = start_time.strftime("%H:%M:%S")  # Update only time
                        components_df.loc[index, 'Status'] = 'InProgress'
                        update_excel(components_df,connection)
                        #start_clock(machine_number)
                        #time.sleep(cycle_time)  # Convert cycle_time to seconds

                        # Check similarity status and determine setup time
                        if similarity_status == 1:
                            last_comp, last_machine, last_op, last_prod = last_processed[machine_number]
                            if last_comp == component and last_machine == machine_number and last_op == operation and last_prod==ProductNames:
                                setup_time = 0  # No setup time needed
                            else:
                                setup_time = row['Setup time (seconds)']  # Setup time is 5 minutes
                        else:
                            setup_time = 0  # No setup time needed

                        print(setup_time)
                        Run_time_r=setup_time + cycle_time
                        time.sleep(Run_time_r)  # Wait for setup time and cycle time

                        # Update the last processed product details
                        last_processed[machine_number] = (component, machine_number, operation, ProductNames)

                        simulated_time += timedelta(seconds=Run_time_r)  # Update simulated time
                        machine_status[machine_number] = 0
                        end_time = simulated_time
                        components_df.loc[index, 'End Time'] = end_time.strftime("%H:%M:%S")  # Update only time
                        components_df.loc[index, 'Status'] = 'Completed'
                        update_runtime(Run_time_r)
                        update_excel(components_df,connection)
                        #stop_clock(machine_number)
            update_excel(components_df,connection)
            time.sleep(1)

            # Collect animation data
            current_time = simulated_time.strftime("%H:%M:%S")
            for i, row in components_df.iterrows():
                animation_data.append(dict(
                    Time=current_time,
                    Product=row['Product Name'],
                    Component=row['Components'],
                    Machine=row['Machine Number'],
                    Status=row['Status']
                ))
            #create_gantt_chart(components_df)

            CurrentTimEnd=datetime.now()
            diff= CurrentTimEnd-CurrentTimeStrt
            simulated_time = simulated_time + diff

def create_gantt_chart(components_df):
    clear_output(wait=True)
    
    # Convert 'Start Time' and 'End Time' columns to datetime
    components_df['Start Time'] = pd.to_datetime(components_df['Start Time'])
    components_df['End Time'] = pd.to_datetime(components_df['End Time'])
    
    # Calculate the duration (difference) between start and end times
    components_df['Duration'] = components_df['End Time'] - components_df['Start Time']

    
    # Prepare data for 2D Gantt chart
    components_df['Start Time'] = components_df['Start Time'].dt.strftime("%Y-%m-%d %H:%M:%S")
    components_df['End Time'] = components_df['End Time'].dt.strftime("%Y-%m-%d %H:%M:%S")

    # Define specific colors for each component
    color_discrete_map = {
        'C1': 'red',
        'C2': 'blue',
        'C3': 'green',
        'C4': 'orange',
        'C5': 'purple',
        # Add more components and colors as needed
    }


    fig = px.timeline(components_df, x_start='Start Time', x_end='End Time', y='Product Name', color='Components', 
                      title='Real-Time 2D Gantt Chart', labels={'Components': 'Component'}, 
                      hover_data={'Duration': '|%H:%M:%S'},color_discrete_map=color_discrete_map)

    fig.update_layout(xaxis_title="Time", yaxis_title="Products")

    
    # Add machine IDs as text inside the rectangles
    for index, row in components_df.iterrows():
        if pd.notnull(row['Start Time']) and pd.notnull(row['End Time']):
            start_time = pd.to_datetime(row['Start Time'])
            end_time = pd.to_datetime(row['End Time'])
            duration = (end_time - start_time) / 2
            mid_time = start_time + duration
            fig.add_annotation(
                x=mid_time.strftime("%Y-%m-%d %H:%M:%S"),
                y=row['Product Name'],
                text=f"{row['Machine Number']}<br>{row['Components']}",
                showarrow=False,
                font=dict(color='black', size=7),
                align='center',
                xanchor='center',
                yanchor='middle'
            )

    #display(fig)
    

def DBConnection():
    
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'  # Correct IP address or hostname
    db_port = '5432'  # Assuming default PostgreSQL port
    db_name = 'ProductDetails'
    # Encode username and password for safe URL inclusion
    encoded_username = urllib.parse.quote_plus(db_username)
    encoded_password = urllib.parse.quote_plus(db_password)

    # Construct the connection URL
    db_url = f'postgresql+psycopg2://{encoded_username}:{encoded_password}@{db_host}:{db_port}/{db_name}'

    try:
        engine = create_engine(db_url)
        connection = engine.connect()
        print("Connection successful!")
    except Exception as e:
        print(f"Connection failed: {e}")
    
    return connection


def main():
        
    #  # Initialize MetaData without reflection
    #     db_username = 'PUser12'
    #     db_password = 'PSQL@123'
    #     db_host = 'localhost'  # Correct IP address or hostname
    #     db_port = '5432'  # Assuming default PostgreSQL port
    #     db_name = 'ProductDetails'
    #     # Encode username and password for safe URL inclusion
    #     encoded_username = urllib.parse.quote_plus(db_username)
    #     encoded_password = urllib.parse.quote_plus(db_password)

    #     # Construct the connection URL
    #     db_url = f'postgresql+psycopg2://{encoded_username}:{encoded_password}@{db_host}:{db_port}/{db_name}'

    #     try:
    #         engine = create_engine(db_url)
    #         connection = engine.connect()
    #         print("Connection successful!")
    #     except Exception as e:
    #         print(f"Connection failed: {e}")
        
      

    #     input_data = sys.stdin.read().strip()
    #     #input_data="Initial"
    #     print(input_data)
    #     if input_data == "Initial":
            
    #         print("Initialization process started.")
    #         components_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='P')
    #         outsource_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Outsource Time')
    #         machines_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Machines')
    #         Similarity_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Similarity')

                       
    #         update_excel(components_df,connection)

    #         allocate_machines(outsource_df, components_df, machines_df, Similarity_df,connection,input_data)
    #     elif input_data == "Start":
    #         print("Start process initiated.")
    #         outsource_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Outsource Time')
    #         machines_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Machines')
    #         Similarity_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Similarity')
    #         components_df=fetch_data()
    #         #print(components_df)
    #         allocate_machines(outsource_df, components_df, machines_df, Similarity_df,connection,input_data)
    #     else:
    #         print(f"Unknown command: {input_data}")
    

    #     components_df=fetch_data()
    #     #print(components_df)
    #     # Convert 'Start Time' and 'End Time' columns to datetime
    #     components_df['Start Time'] = pd.to_datetime(components_df['Start Time'])
    #     components_df['End Time'] = pd.to_datetime(components_df['End Time'])

    #     # Calculate the duration (difference) between start and end times
    #     components_df['Time Diff'] = components_df['End Time'] - components_df['Start Time']

    #     print(components_df)
    #     # Fixed total time (start time in this case)
    #     total_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)

    #     # Calculate Idle Time
    #     components_df['Idle Time'] = total_time - components_df['Time Diff']

    #     # Format Idle Time to %H:%M:%S
    #     components_df['Idle Time'] = components_df['Idle Time'].dt.strftime('%H:%M:%S')
    #     print(components_df)
    #     #update_excel(components_df,connection)
    #     # Format 'Time Diff' to %H:%M:%S
    #     components_df['Time Diff'] = components_df['Time Diff'].dt.total_seconds().apply(lambda x: pd.Timedelta(seconds=x)).dt.floor('s').astype(str)
    #     components_df['Time Diff'] = components_df['Time Diff'].apply(lambda x: str(x).split(' ')[-1])
        
    #     update_excel(components_df,connection)

        outsource_df = pd.read_excel('Product Details_v1.xlsx', sheet_name='Outsource Time')
        dash_table.DataTable(data=outsource_df)

if __name__ == "__main__":
    main()
