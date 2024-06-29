import psycopg2
import dash
from dash import dcc, html, Input, Output, dash_table
from dash.dependencies import Input, Output,State
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import dash_bootstrap_components as dbc  # Import dash-bootstrap-components
import subprocess
import os
import signal  # Import the signal module
from dash import callback_context
from dash.exceptions import PreventUpdate
from psycopg2 import sql
import threading
import time
import json
import queue
from Allocation_check import output_queue
from multiprocessing import Process, Queue, get_context
import sys
print("Python version")
print(sys.version)
print("Version info.")
print(sys.version_info)

allocation_process=None
# Global variable to track interruption status
allocation_interrupted = False
Dash_time=None
# Database connection details
db_name = 'ProductDetails'
db_username = 'PUser12'
db_password = 'PSQL@123'
db_host = 'localhost'
db_port = '5432'
global flag1
# Function to start allocation process in a separate thread


# Function to fetch data from the database
def fetch_data():
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        query = '''SELECT * FROM public."prodet";'''
        df = pd.read_sql(query, conn)
        conn.close()
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame() 

# Function to fetch data from the database
def fetch_data1():
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        query = '''SELECT * FROM public."prodet";'''
        df = pd.read_sql(query, conn)
        conn.close()

        # Determine if any component of the product is not editable
        df['editable'] = df.groupby('Product Name')['Status'].transform(lambda x: not any(status in ['Completed', 'InProgress'] for status in x))

        # Filter the dataframe to include only products where all components are editable
        editable_df = df[df['editable']].drop(columns=['editable'])
        print(editable_df)
        return editable_df
        #return df

    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame() 

# Function to convert time string to timedelta
def time_to_timedelta2(t):
    try:
        if isinstance(t, datetime):
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        if pd.isna(t) or t == "":
            return timedelta(0)
        # Ensure t is a string and in the format "HH:MM:SS"
        if isinstance(t, str) and ':' in t:
            h, m, s = map(int, t.split(":"))
            return timedelta(hours=h, minutes=m, seconds=s)
        else:
            # Handle unexpected input format or missing ':'
            raise ValueError(f"Unexpected format or missing ':' in input: {t}")
    except Exception as e:
        print(f"Error in time_to_timedelta2: {e}")
        return timedelta(0)  # or raise further or return appropriate default

# Function to calculate utilization in minutes
def calculate_utilization(t):
    total_seconds = t.total_seconds()
    return total_seconds / 60


# Function to fetch previous data from the database
def fetch_previous_data_from_db(db_name, db_username, db_password, db_host, db_port):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        
        query = 'SELECT * FROM public."prodet"'
        df = pd.read_sql_query(query, conn)
        conn.close()
        previous_data = df.to_dict('records')
        return previous_data
    except Exception as e:
        print(f"Error fetching data from database: {e}")
        return []
    
# Function to get the last unique ID from the database
def get_last_unique_id(table_name):
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_username,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cursor = conn.cursor()
    if table_name=="prodet":
        query = '''SELECT "UniqueID" FROM public."prodet" ORDER BY "UniqueID" DESC LIMIT 1;'''
    else:
        query = '''SELECT "UniqueID" FROM public."Addln" ORDER BY "UniqueID" DESC LIMIT 1;'''
    cursor.execute(query)
    last_id = cursor.fetchone()
    cursor.close()
    conn.close()
    if last_id:
        return int(last_id[0])
    else:
        return 0  # Return 0 if there are no entries in the database


# Convert necessary fields to string
def convert_data_for_json(data):
    for record in data:
        for key, value in record.items():
            if isinstance(value, pd.Timestamp):
                record[key] = value.strftime('%Y-%m-%d %H:%M:%S')
            elif isinstance(value, (pd.Timedelta, pd.TimedeltaIndex)):
                record[key] = str(value)
            elif pd.isna(value):  # Convert NaN to None for JSON serialization
                record[key] = None
    return data

initial_data = fetch_data1().to_dict('records')
initial_data_json = json.dumps(initial_data, default=str)

# Initialize the starting time to 09:00:00
start_time = datetime.combine(datetime.today(), datetime.min.time()) + timedelta(hours=9)

# Define button style
button_style = {
    'margin': '10px',
    'padding': '15px 30px',
    'font-size': '16px',
    'font-weight': 'bold',
    'border-radius': '8px',
    'background-color': '#3498db',
    'color': 'white',
    'border': 'none',
    'cursor': 'pointer',
    'transition': 'background-color 0.3s ease',
}

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.SLATE])
app.config.suppress_callback_exceptions = True
# Define layout
app.layout = dbc.Container(
    style={'textAlign': 'left', 'width': '100%', 'margin': 'auto'},
    children=[
        html.Div(style={'height': '50px'}),
        html.H1('Dashboard - Production Analysis', style={'textAlign': 'center', 'marginBottom': '30px'}),
        
        dbc.Card(
            id='info-box',
            style={
                'padding': '5px',
                'border': '7px solid #ddd',
                'borderRadius': '15px',
                'backgroundColor': '#3498db',  # Blue color
                'color': 'white',  # Text color
                'textAlign': 'center',  # Center align content inside the box
                'position': 'absolute',
                'left': '20px',
                'top': '25px',
                'width': '250px',  # Adjust width as needed
            },
            children=[
                html.Div(id='live-clock', style={'fontSize': 25, 'textAlign': 'center'}),
                html.Div(id='current-date', style={'fontSize': 18, 'textAlign': 'center'}),
                html.Div(id='current-day', style={'fontSize': 18, 'textAlign': 'center'})
            ]
        ),
        
        dcc.Interval(
            id='interval-component-clock',
            interval=1000,  # Update clock every second
            n_intervals=0
        ),
        
        dcc.Interval(
            id='interval-component-script',
            interval=1000,  # Update script control every second
            n_intervals=0,
            disabled=True  # Start disabled
        ),
        
        dbc.Row([
            dbc.Col([
                html.Button('Read from spreadsheet', id='initialise-button', n_clicks=0, style=button_style),
                html.Button('Run/Reschedule', id='start-button', n_clicks=0, style=button_style),
                html.Button('Pause', id='stop-button', n_clicks=0, style=button_style),
                html.Div(id='start-message', style={'marginLeft': '20px', 'color': 'green'})
            ], width=15, style={'textAlign': 'Right', 'margin': 'auto'})
        ]),
        
        dcc.Tabs(id='tabs', value='tab-input', children=[
            dcc.Tab(label='Product List change', value='tab-manage-products', children=[
                dbc.Row([
                    dbc.Col(
                        dcc.Dropdown(
                            id='manage-dropdown',
                            options=[
                                {'label': 'Add Product', 'value': 'add'},
                                {'label': 'Delete Product', 'value': 'delete'},
                                {'label': 'Swap Product', 'value': 'swap'}
                            ],
                            value='add',
                            placeholder='Select action',
                            style={'width': '200px'}
                        ),
                        width=3,
                        style={'padding': '20px'}
                    ),
                    dbc.Col(
                        html.Div(id='manage-content'),
                        width=9
                    )
                ])
            ]),
            
            dcc.Tab(label='Product Catalogue', value='tab-2', children=[
                html.H2('Below are the product details', style={'textAlign': 'left', 'marginBottom': '30px', 'fontSize': '20px'}),
                html.Div([
                    dash_table.DataTable(
                        id='data-table',
                        columns=[],
                        data=[],
                        filter_action='native',
                        sort_action="native",
                        page_size=10,
                        style_table={'height': '400px', 'overflowY': 'auto', 'marginBottom': '20px'},
                        style_cell={
                            'textAlign': 'center',
                            'padding': '5px',
                            'backgroundColor': '#f9f9f9',
                            'border': '1px solid black',
                            'minWidth': '120px', 'maxWidth': '150px', 'whiteSpace': 'normal'
                        },
                        style_header={
                            'backgroundColor': '#4CAF50',
                            'fontWeight': 'bold',
                            'color': 'white',
                            'border': '1px solid black'
                        },
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': '#f2f2f2',
                            }
                        ],
                        tooltip_data=[
                            {
                                column: {'value': str(value), 'type': 'markdown'}
                                for column, value in row.items()
                            } for row in fetch_data().to_dict('records')
                        ],
                        tooltip_duration=None,
                        css=[{
                            'selector': '.dash-cell div.dash-cell-value',
                            'rule': 'display: inline; white-space: inherit; overflow: inherit; text-overflow: inherit;'
                        }]
                    ),
                    dcc.Interval(
                        id='interval-component-table',
                        interval=5000,
                        n_intervals=0
                    )
                ])
            ]),
            
            # Modify Tab
            dcc.Tab(label='Modify', value='tab-modify', children=[
                dcc.Tabs(id='modify-sub-tabs', value='tab-inhouse', children=[
                dcc.Tab(label='InHouse', value='tab-inhouse', children=[
                    html.Div([
                        html.H2('Modify InHouse Product Data', style={'textAlign': 'left', 'marginBottom': '20px','marginTop': '20px', 'fontSize': '15px'}),
                        
                        dbc.Row([
                            dbc.Col(
                                dcc.Dropdown(
                                    id='inhouse-product-dropdown',
                                    placeholder='Select Product Name',
                                    style={'marginBottom': '20px'}
                                ),
                                width=3
                            ),
                            
                            dbc.Col(
                                dcc.Dropdown(
                                    id='inhouse-component-dropdown',
                                    placeholder='Select Component',
                                    style={'marginBottom': '20px'}
                                ),
                                width=3
                            )
                        ]),
                        
                        dbc.Row([
                            dbc.Col(
                                dcc.Dropdown(
                                    id='inhouse-column-dropdown',
                                    placeholder='Select Column to Edit',
                                    style={'marginBottom': '20px'}
                                ),width=4
                            )
                        ]),
                        
                        dbc.Row([
                            dbc.Col(
                                dbc.Input(
                                    id='inhouse-value-input',
                                    placeholder='Enter New Value',
                                    type='text',
                                    style={'marginBottom': '20px'}
                                ),
                                width=6
                            ),
                            dbc.Col(
                                html.Button('Confirm Changes', id='inhouse-confirm-changes-button', n_clicks=0, style={'marginTop': '20px'}),
                                width=6
                            )
                        ]),
                        
                        html.Div(id='inhouse-confirm-message', style={'marginTop': '20px', 'color': 'green', 'fontWeight': 'bold'}),

                         # DataTable to display selected data
                        html.Div([
                            dash_table.DataTable(
                                id='inhouse-selected-data-table',
                                columns=[
                                    {'name': 'UniqueID', 'id': 'UniqueID'},
                                    {'name': 'Product Name', 'id': 'Product Name'},
                                    {'name': 'Order Processing Date', 'id': 'Order Processing Date'},
                                    {'name': 'Promised Delivery Date', 'id': 'Promised Delivery Date'},
                                    {'name': 'Quantity Required', 'id': 'Quantity Required'},
                                    {'name': 'Components', 'id': 'Components'},
                                    {'name': 'Operation', 'id': 'Operation'},
                                    {'name': 'Process Type', 'id': 'Process Type'},
                                    {'name': 'Machine Number', 'id': 'Machine Number'},
                                    {'name': 'Run Time (min/1000)', 'id': 'Run Time (min/1000)'},
                                    {'name': 'Start Time', 'id': 'Start Time'},
                                    {'name': 'End Time', 'id': 'End Time'},
                                    {'name': 'Status', 'id': 'Status'}
                                ],
                                data=[],  # Initially empty until products and components are selected
                                style_table={'height': '400px', 'overflowY': 'auto'},
                                style_header={
                                    'backgroundColor': 'rgb(230, 230, 230)',
                                    'fontWeight': 'bold'
                                },
                                style_cell={
                                    'textAlign': 'left',
                                    'minWidth': '100px',
                                    'maxWidth': '180px',
                                    'whiteSpace': 'normal'
                                },
                                style_data_conditional=[
                                    {
                                        'if': {'row_index': 'odd'},
                                        'backgroundColor': 'rgb(248, 248, 248)'
                                    },
                                    {
                                        'if': {'column_id': 'Status', 'filter_query': '{Status} = "Delayed"'},
                                        'backgroundColor': 'tomato',
                                        'color': 'white',
                                        'fontWeight': 'bold'
                                    }
                                ],
                                page_size=10,
                                sort_action='native',
                                filter_action='native',
                                column_selectable='single',
                                row_selectable='single',
                                selected_columns=[],
                                selected_rows=[],
                                editable=True
                            )
                        ])
                    ])
                ]),
                dcc.Tab(label='Outsource', value='tab-outsource', children=[
                    html.Div([
                        html.H2('Modify Outsource Product Data', style={'textAlign': 'left', 'marginBottom': '20px', 'marginTop': '20px', 'fontSize': '15px'}),
                        
                        dbc.Row([
                            dbc.Col(
                                dcc.Dropdown(
                                    id='outsource-product-dropdown',
                                    placeholder='Select Product Name',
                                    style={'marginBottom': '20px'}
                                ),
                                width=3
                            ),
                            
                            dbc.Col(
                                dcc.Dropdown(
                                    id='outsource-component-dropdown',
                                    placeholder='Select Component',
                                    style={'marginBottom': '20px'}
                                ),
                                width=3
                            )
                        ]),
                        
                        dbc.Row([
                            dbc.Col(
                                dcc.Dropdown(
                                    id='outsource-column-dropdown',
                                    placeholder='Select Column to Edit',
                                    style={'marginBottom': '20px'}
                                ),width=4
                            )
                        ]),
                        
                        dbc.Row([
                            dbc.Col(
                                dbc.Input(
                                    id='outsource-value-input',
                                    placeholder='Enter New Value',
                                    type='text',
                                    style={'marginBottom': '20px'}
                                ),
                                width=6
                            ),
                            dbc.Col(
                                html.Button('Confirm Changes', id='outsource-confirm-changes-button', n_clicks=0, style={'marginTop': '20px'}),
                                width=6
                            )
                        ]),
                        
                        html.Div(id='outsource-confirm-message', style={'marginTop': '20px', 'color': 'green', 'fontWeight': 'bold'}),

                        # DataTable to display selected data
                        html.Div([
                            dash_table.DataTable(
                                id='outsource-selected-data-table',
                                columns=[
                                    {'name': 'UniqueID', 'id': 'UniqueID'},
                                    {'name': 'Product Name', 'id': 'Product Name'},
                                    {'name': 'Order Processing Date', 'id': 'Order Processing Date'},
                                    {'name': 'Promised Delivery Date', 'id': 'Promised Delivery Date'},
                                    {'name': 'Quantity Required', 'id': 'Quantity Required'},
                                    {'name': 'Components', 'id': 'Components'},
                                    {'name': 'Operation', 'id': 'Operation'},
                                    {'name': 'Process Type', 'id': 'Process Type'},
                                    {'name': 'Machine Number', 'id': 'Machine Number'},
                                    {'name': 'Run Time (min/1000)', 'id': 'Run Time (min/1000)'},
                                    {'name': 'Start Time', 'id': 'Start Time'},
                                    {'name': 'End Time', 'id': 'End Time'},
                                    {'name': 'Status', 'id': 'Status'}
                                ],
                                data=[],  # Initially empty until products and components are selected
                                style_table={'height': '400px', 'overflowY': 'auto', 'marginBottom': '20px'},
                                style_header={
                                    'backgroundColor': 'rgb(230, 230, 230)',
                                    'fontWeight': 'bold'
                                },
                                style_cell={
                                    'textAlign': 'left',
                                    'minWidth': '100px',
                                    'maxWidth': '180px',
                                    'whiteSpace': 'normal'
                                },
                                style_data_conditional=[
                                    {
                                        'if': {'row_index': 'odd'},
                                        'backgroundColor': 'rgb(248, 248, 248)'
                                    },
                                    {
                                        'if': {'column_id': 'Status', 'filter_query': '{Status} = "Delayed"'},
                                        'backgroundColor': 'tomato',
                                        'color': 'white',
                                        'fontWeight': 'bold'
                                    }
                                ],
                                page_size=10,
                                sort_action='native',
                                filter_action='native',
                                column_selectable='single',
                                row_selectable='single',
                                selected_columns=[],
                                selected_rows=[],
                                editable=True
                            )
                        ])
                    ])
                ])
            ])
            ]),
            
            dcc.Tab(label='Visualize', value='tab-output', children=[
                html.Div(
                    "Select a plot to display:",
                    style={'textAlign': 'center', 'fontSize': '18px', 'marginTop': '20px'}
                ),
                dcc.Dropdown(
                    id='plot-dropdown',
                    options=[
                        {'label': 'Gantt Chart', 'value': 'Gantt Chart'},
                        {'label': 'Utilization', 'value': 'Utilization'},
                        {'label': 'Time Taken by each Machine', 'value': 'Time Taken by each Machine'},
                        {'label': 'Time taken by each product', 'value': 'Time taken by each product'},
                        {'label': 'Wait Time', 'value': 'Wait Time'},
                        {'label': 'Idle Time', 'value': 'Idle Time'},
                        {'label': 'Product Components Status', 'value': 'Product Components Status'},
                        {'label': 'Remaining Time', 'value': 'Remaining Time'}
                    ],
                    value='Gantt Chart',
                    style={'width': '50%', 'margin': '15px auto'}
                ),
                dcc.Graph(
                    id='main-graph',
                    style={'width': '90%', 'margin': 'auto', 'marginTop': '50px', 'marginBottom': '50px'}
                ),
                dcc.Interval(
                    id='interval-component-data',
                    interval=5000,  # Update data and chart every 5 seconds (adjust as needed)
                    n_intervals=0
                )
            ])
        ], style={'marginTop': '50px', 'marginBottom': '50px'})
    ]
)


@app.callback(
    Output('manage-content', 'children'),
    Input('manage-dropdown', 'value')
)
def render_manage_content(action):
    if action == 'add':
        return html.Div(
            id='input-form',
            children=[
                html.H2('Add New Product', style={'textAlign': 'left', 'marginBottom': '30px', 'fontSize': '20px'}),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Sr. No:"),
                        dbc.Input(id='Sr-No', type='number', placeholder='Enter product number (Product 1, Product 2, ...)'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Product Name:"),
                        dbc.Input(id='Product-Name', type='text', placeholder='Enter product name'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Order Processing Date:"),
                        dbc.Input(id='Order-Processing-Date', type='date', placeholder='Enter processing date'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Promised Delivery Date:"),
                        dbc.Input(id='Promised-Delivery-Date', type='date', placeholder='Enter delivery date'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Quantity Required:"),
                        dbc.Input(id='Quantity-Required', type='number', placeholder='Enter required quantity'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Components:"),
                        dbc.Input(id='Components', type='text', placeholder='Enter components'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Operation:"),
                        dbc.Input(id='Operation', type='text', placeholder='Enter operation'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                            [
                                dbc.InputGroupText("Process Type:"),
                                dcc.Dropdown(
                                    id='Process-Type',
                                    options=[
                                        {'label': 'In House', 'value': 'In House'},
                                        {'label': 'Outsource', 'value': 'Outsource'}
                                    ],
                                    placeholder='Select process type...',
                                    style={'width': '70%'}  # Adjust width as needed
                                ),
                            ],
                            style={'marginBottom': '10px'}
                        ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Machine Number:"),
                        dbc.Input(id='Machine-Number', type='text', placeholder='Enter machine number'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Run Time (min/1000):"),
                        dbc.Input(id='Run-Time', type='number', placeholder='Enter run time'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Cycle Time (seconds):"),
                        dbc.Input(id='Cycle-Time', type='number', placeholder='Enter cycle time'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Setup time (seconds):"),
                        dbc.Input(id='Setup-Time', type='number', placeholder='Enter setup time'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                html.Button('Submit', id='submit-button', n_clicks=0, style={'marginTop': '10px'}),
                html.Div(id='submit-output', style={'marginTop': '10px'})
            ]
        )

    elif action == 'delete':
        return html.Div(
            id='input-form',
            children=[
                html.H2('Delete Product', style={'textAlign': 'left', 'marginBottom': '30px', 'fontSize': '20px'}),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("UniqueID:"),
                        dbc.Input(id='UniqueID-delete', type='number', placeholder='Enter UniqueID to delete'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                html.Button('Delete', id='delete-button', n_clicks=0, style={'marginTop': '10px'}),
                html.Div(id='delete-output', style={'marginTop': '10px'})
            ]
        )

    elif action == 'swap':
        return html.Div(
            id='input-form',
            children=[
                html.H2('Swap Product', style={'textAlign': 'left', 'marginBottom': '30px', 'fontSize': '20px'}),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("First UniqueID:"),
                        dbc.Input(id='UniqueID-swap1', type='number', placeholder='Enter first UniqueID'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                dbc.InputGroup(
                    [
                        dbc.InputGroupText("Second UniqueID:"),
                        dbc.Input(id='UniqueID-swap2', type='number', placeholder='Enter second UniqueID'),
                    ],
                    style={'marginBottom': '10px'}
                ),
                html.Button('Swap', id='swap-button', n_clicks=0, style={'marginTop': '10px'}),
                html.Div(id='swap-output', style={'marginTop': '10px'})
            ]
        )

    else:
        return html.Div()


# Callback to add new product
@app.callback(
    Output('submit-output', 'children'),
    Input('submit-button', 'n_clicks'),
    State('Sr-No', 'value'),
    State('Product-Name', 'value'),
    State('Order-Processing-Date', 'value'),
    State('Promised-Delivery-Date', 'value'),
    State('Quantity-Required', 'value'),
    State('Components', 'value'),
    State('Operation', 'value'),
    State('Process-Type', 'value'),
    State('Machine-Number', 'value'),
    State('Run-Time', 'value'),
    State('Cycle-Time', 'value'),
    State('Setup-Time', 'value')
)
def add_new_product(n_clicks, sr_no, product_name, processing_date, delivery_date, quantity_required,
                    components, operation, process_type, machine_number, run_time, cycle_time, setup_time):
    if n_clicks > 0:
        try:
            # Check if "Addln" table is empty
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_username,
                password=db_password,
                host=db_host,
                port=db_port
            )
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM public.\"Addln\"")
            addln_count = cursor.fetchone()[0]

            if addln_count == 0:
                # If "Addln" table is empty, get last ID from "prodet"
                last_id = get_last_unique_id("prodet")
            else:
                # Otherwise, get last ID from "Addln"
                last_id = get_last_unique_id("Addln")

            new_id = last_id + 1  # Increment the last ID by 1

            cursor.close()
            conn.close()

            conn = psycopg2.connect(
                dbname=db_name,
                user=db_username,
                password=db_password,
                host=db_host,
                port=db_port
            )
            cursor = conn.cursor()

            cursor.execute('INSERT INTO public."Addln" ( "UniqueID","Sr. No", "Product Name", "Order Processing Date", \
                            "Promised Delivery Date", "Quantity Required", "Components", "Operation", \
                            "Process Type", "Machine Number", "Run Time (min/1000)", "Cycle Time (seconds)", \
                            "Setup time (seconds)") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
                           (new_id, sr_no, product_name, processing_date, delivery_date, quantity_required,
                            components, operation, process_type, machine_number, run_time, cycle_time, setup_time))
            conn.commit()

            cursor.close()
            conn.close()

            return dbc.Alert("Product added successfully", color="success", dismissable=True)

        except Exception as e:
            return dbc.Alert(f"Error adding product: {e}", color="danger", dismissable=True)

    return html.Div()


# Callback to delete product
@app.callback(
    Output('delete-output', 'children'),
    Input('delete-button', 'n_clicks'),
    State('UniqueID-delete', 'value')
)
def delete_product(n_clicks, unique_id):
    if n_clicks > 0:
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_username,
                password=db_password,
                host=db_host,
                port=db_port
            )
            cursor = conn.cursor()

            cursor.execute('DELETE FROM public."prodet" WHERE "UniqueID" = %s', (unique_id,))
            conn.commit()

            cursor.close()
            conn.close()

            return dbc.Alert("Product deleted successfully", color="success", dismissable=True)

        except Exception as e:
            return dbc.Alert(f"Error deleting product: {e}", color="danger", dismissable=True)

    return html.Div()


# Callback to swap products
@app.callback(
    Output('swap-output', 'children'),
    Input('swap-button', 'n_clicks'),
    State('UniqueID-swap1', 'value'),
    State('UniqueID-swap2', 'value')
)
def swap_products(n_clicks, unique_id1, unique_id2):
    if n_clicks > 0:
        try:
            conn = psycopg2.connect(
                dbname=db_name,
                user=db_username,
                password=db_password,
                host=db_host,
                port=db_port
            )
            cursor = conn.cursor()
            query1 = '''SELECT * FROM public."prodet" WHERE "UniqueID" = %s'''
            query2 = '''SELECT * FROM public."prodet" WHERE "UniqueID" = %s'''
            cursor.execute(query1, (unique_id1,))
            product1 = cursor.fetchone()
            cursor.execute(query2, (unique_id2,))
            product2 = cursor.fetchone()
            if product1 and product2:
                query3 = '''UPDATE public."prodet" SET "Sr. No" = %s, "Product Name" = %s, "Order Processing Date" = %s, "Promised Delivery Date" = %s, "Quantity Required" = %s,
                "Components" = %s, "Operation" = %s, "Process Type" = %s, "Machine Number" = %s, "Run Time (min/1000)" = %s, "Cycle Time (seconds)" = %s, "Setup time (seconds)" = %s
                WHERE "UniqueID" = %s'''
                cursor.execute(query3, (product2[1], product2[2], product2[3], product2[4], product2[5], product2[6], product2[7], product2[8], product2[9], product2[10], product2[11], product2[12], unique_id1))
                cursor.execute(query3, (product1[1], product1[2], product1[3], product1[4], product1[5], product1[6], product1[7], product1[8], product1[9], product1[10], product1[11], product1[12], unique_id2))
                conn.commit()
                cursor.close()
                conn.close()
                return f'Products with Unique IDs {unique_id1} and {unique_id2} swapped successfully!'
            else:
                return 'One or both products not found!'

        except Exception as e:
            return dbc.Alert(f"Error swapping products: {e}", color="danger", dismissable=True)

    return html.Div()


def fetch_data_Details1(product_name=None, component_name=None):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        query = '''
            SELECT 
                "UniqueID",
                "Product Name", 
                "Order Processing Date", 
                "Promised Delivery Date", 
                "Quantity Required", 
                "Components",
                "Operation",
                "Process Type",
                "Machine Number",
                "Run Time (min/1000)",
                "Start Time",
                "End Time",
                "Status"
            FROM public."prodet"
            ORDER BY "UniqueID";
        '''
        
        
        df = pd.read_sql(query, conn)

        conn.close()
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()

@app.callback(
    Output('data-table', 'columns'),
    Output('data-table', 'data'),
    Input('interval-component-table', 'n_intervals')
)
def update_table(n_intervals):
    df = fetch_data_Details1()
    columns = [{'name': col, 'id': col} for col in df.columns]
    data = df.to_dict('records')
    return columns, data


def fetch_data_Details(product_name=None, component_name=None):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        query = '''
            SELECT 
                "UniqueID",
                "Product Name", 
                "Order Processing Date", 
                "Promised Delivery Date", 
                "Quantity Required", 
                "Components",
                "Operation",
                "Process Type",
                "Machine Number",
                "Run Time (min/1000)",
                "Start Time",
                "End Time",
                "Status"
            FROM public."prodet"
        '''
        
        if product_name and component_name:
            query += ' WHERE "Product Name" = %s AND "Components" = %s'
            df = pd.read_sql(query, conn, params=(product_name, component_name))
        elif product_name:
            query += ' WHERE "Product Name" = %s'
            df = pd.read_sql(query, conn, params=(product_name,))
        elif component_name:
            query += ' WHERE "Components" = %s'
            df = pd.read_sql(query, conn, params=(component_name,))
        else:
            df = pd.read_sql(query, conn)

        conn.close()
        return df
    except Exception as e:
        print(f"Error fetching data: {e}")
        return pd.DataFrame()



# Sample function to update database
def modify_DB(unique_id, column_name, new_value, db_name, db_username, db_password, db_host, db_port):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        cursor = conn.cursor()
        
        # Perform update based on unique_id, column_name, and new_value
        query = sql.SQL('UPDATE public."prodet" SET {} = %s WHERE "UniqueID" = %s').format(sql.Identifier(column_name))
        cursor.execute(query, (new_value, unique_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error updating database: {e}")
        return False

def fetch_products_and_components(process_type, db_name, db_username, db_password, db_host, db_port):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        cursor = conn.cursor()
        print(process_type)
        if process_type == 'In House':
            cursor.execute('SELECT DISTINCT "Product Name" FROM public."prodet" WHERE "Process Type" = %s', (process_type,))
            product_names = [row[0] for row in cursor.fetchall()]
            cursor.execute('SELECT DISTINCT "Components" FROM public."prodet" WHERE "Process Type" = %s', (process_type,))
            components = [row[0] for row in cursor.fetchall()]
        elif process_type == 'Outsource':
            cursor.execute('SELECT DISTINCT "Product Name" FROM public."prodet" WHERE "Process Type" = %s', (process_type,))
            product_names = [row[0] for row in cursor.fetchall()]
            cursor.execute('SELECT DISTINCT "Components" FROM public."prodet" WHERE "Process Type" = %s', (process_type,))
            components = [row[0] for row in cursor.fetchall()]
        else:
            product_names = []
            components = []

        cursor.close()
        conn.close()

        return product_names, components
    except Exception as e:
        print(f"Error fetching products and components: {e}")
        return [], []


def fetch_unique_id(product_name, component, process_type, db_name, db_username, db_password, db_host, db_port):
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        cursor = conn.cursor()
        
        query = '''
            SELECT "UniqueID"
            FROM public."prodet"
            WHERE "Product Name" = %s AND "Components" = %s AND "Process Type" = %s
        '''
        cursor.execute(query, (product_name, component, process_type))
        result = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if result:
            return result[0]
        else:
            return None
    except Exception as e:
        print(f"Error fetching UniqueID: {e}")
        return None


# Callback to update product dropdown options for InHouse
@app.callback(
    Output('inhouse-product-dropdown', 'options'),
    Input('modify-sub-tabs', 'value')
)
def update_inhouse_product_dropdown(tab):
    if tab != 'tab-inhouse':
        raise PreventUpdate
    
    db_name = 'ProductDetails'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'
    db_port = '5432'

    product_names, _ = fetch_products_and_components('In House', db_name, db_username, db_password, db_host, db_port)
    
    options = [{'label': name, 'value': name} for name in product_names]
    
    return options

# Callback to update component dropdown options for InHouse based on selected product
@app.callback(
    Output('inhouse-component-dropdown', 'options'),
    Input('inhouse-product-dropdown', 'value')
)
def update_inhouse_component_dropdown(product_name):
    if product_name is None:
        raise PreventUpdate
    
    db_name = 'ProductDetails'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'
    db_port = '5432'
    
    # Fetch components for the selected product
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_username,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cursor = conn.cursor()
    
    query = '''
        SELECT DISTINCT "Components"
        FROM public."prodet"
        WHERE "Product Name" = %s AND "Process Type" = 'In House'
    '''
    cursor.execute(query, (product_name,))
    components = [row[0] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    options = [{'label': comp, 'value': comp} for comp in components]
    
    return options

# Callback to update column dropdown options for InHouse
@app.callback(
    Output('inhouse-column-dropdown', 'options'),
    Input('inhouse-product-dropdown', 'value'),
    Input('inhouse-component-dropdown', 'value')
)
def update_inhouse_column_dropdown(product_name, component_name):
    if product_name is None or component_name is None:
        raise PreventUpdate
    
    columns = ['Product Name', 'Order Processing Date', 'Promised Delivery Date', 'Quantity Required', 'Components', 'Operation', 'Process Type', 'Machine Number', 'Run Time (min/1000)', 'Cycle Time (seconds)', 'Setup time (seconds)']
    
    options = [{'label': col, 'value': col} for col in columns]
    
    return options


# Callback to handle database update on button click for InHouse
@app.callback(
    Output('inhouse-confirm-message', 'children'),
    Input('inhouse-confirm-changes-button', 'n_clicks'),
    State('inhouse-product-dropdown', 'value'),
    State('inhouse-component-dropdown', 'value'),
    State('inhouse-column-dropdown', 'value'),
    State('inhouse-value-input', 'value')
)
def update_inhouse_database(n_clicks, product_name, component_name, column_name, new_value):
    if n_clicks == 0:
        raise PreventUpdate
    
    if product_name is None or component_name is None or column_name is None or new_value is None:
        return "Please fill all fields."
    
    db_name = 'ProductDetails'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'
    db_port = '5432'
    

    unique_id = fetch_unique_id(product_name, component_name,"In House",db_name, db_username, db_password, db_host, db_port)
    success = modify_DB(unique_id, column_name, new_value, db_name, db_username, db_password, db_host, db_port)
    
    if success:
        return f"Successfully updated {column_name} for {product_name}/{component_name} to {new_value}."
    else:
        return "Error updating database. Please try again."

# Repeat similar callbacks for Outsource

# Callback to update product dropdown options for Outsource
@app.callback(
    Output('outsource-product-dropdown', 'options'),
    Input('modify-sub-tabs', 'value')
)
def update_outsource_product_dropdown(tab):
    if tab != 'tab-outsource':
        raise PreventUpdate
    
    db_name = 'ProductDetails'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'
    db_port = '5432'

    product_names, _ = fetch_products_and_components('Outsource', db_name, db_username, db_password, db_host, db_port)
    
    options = [{'label': name, 'value': name} for name in product_names]
    
    return options

# Callback to update component dropdown options for Outsource
@app.callback(
    Output('outsource-component-dropdown', 'options'),
    Input('outsource-product-dropdown', 'value')
)
def update_outsource_component_dropdown(product_name):
    if product_name is None:
        raise PreventUpdate
    
    db_name = 'ProductDetails'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'
    db_port = '5432'
    
    # Fetch components for the selected product
    conn = psycopg2.connect(
        dbname=db_name,
        user=db_username,
        password=db_password,
        host=db_host,
        port=db_port
    )
    cursor = conn.cursor()
    
    query = '''
        SELECT DISTINCT "Components"
        FROM public."prodet"
        WHERE "Product Name" = %s AND "Process Type" = 'Outsource'
    '''
    cursor.execute(query, (product_name,))
    components = [row[0] for row in cursor.fetchall()]
    
    cursor.close()
    conn.close()
    
    options = [{'label': comp, 'value': comp} for comp in components]
    
    return options
    

# Callback to update column dropdown options for Outsource
@app.callback(
    Output('outsource-column-dropdown', 'options'),
    Input('outsource-product-dropdown', 'value'),
    Input('outsource-component-dropdown', 'value')
)
def update_outsource_column_dropdown(product_name, component_name):
    if product_name is None or component_name is None:
        raise PreventUpdate
    
    columns = ['Run Time (min/1000)']
    
    options = [{'label': col, 'value': col} for col in columns]
    
    return options

# Callback to handle database update on button click for Outsource
@app.callback(
    Output('outsource-confirm-message', 'children'),
    Input('outsource-confirm-changes-button', 'n_clicks'),
    State('outsource-product-dropdown', 'value'),
    State('outsource-component-dropdown', 'value'),
    State('outsource-column-dropdown', 'value'),
    State('outsource-value-input', 'value')
)
def update_outsource_database(n_clicks, product_name, component_name, column_name, new_value):
    if n_clicks == 0:
        raise PreventUpdate
    
    if product_name is None or component_name is None or column_name is None or new_value is None:
        return "Please fill all fields."
    
    db_name = 'ProductDetails'
    db_username = 'PUser12'
    db_password = 'PSQL@123'
    db_host = 'localhost'
    db_port = '5432'
    
    unique_id = fetch_unique_id(product_name, component_name,"Outsource",db_name, db_username, db_password, db_host, db_port)
    success = modify_DB(unique_id, column_name, new_value, db_name, db_username, db_password, db_host, db_port)
    
    if success:
        return f"Successfully updated {column_name} for {product_name}/{component_name} to {new_value}."
    else:
        return "Error updating database. Please try again."


# Callback to update the data table based on product and component selection for InHouse
@app.callback(
    Output('inhouse-selected-data-table', 'data'),
    Input('inhouse-product-dropdown', 'value'),
    Input('inhouse-component-dropdown', 'value')
)
def update_inhouse_selected_data_table(product_name, component_name):
    print(product_name)
    print(component_name)
    if product_name and component_name:
        df = fetch_data_Details(product_name, component_name)
        data = df.to_dict('records')
        return data
    else:
        return []
# Callback to update the data table based on product and component selection for Outsource
@app.callback(
    Output('outsource-selected-data-table', 'data'),
    Input('outsource-product-dropdown', 'value'),
    Input('outsource-component-dropdown', 'value')
)
def update_outsource_selected_data_table(product_name, component_name):
    if product_name and component_name:
        df = fetch_data_Details(product_name, component_name)
        data = df.to_dict('records')
        return data
    else:
        return []

# Function to read the stdout and stderr
def read_output(process):
    while True:
        output = process.stdout.readline()
        if output:
            print(output.strip())
        error = process.stderr.readline()
        if error:
            print(f"ERROR: {error.strip()}")
        if output == '' and process.poll() is not None:
            break

def start_allocation_check(keyword):
    global allocation_process
    
    try:
        allocation_process = subprocess.Popen(
            ['python', 'Allocation_check.py'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line-buffered mode
        )
        stdout, stderr = allocation_process.communicate(keyword)
        #print("Script output:", stdout)
        #print("Script error:", stderr)
        threading.Thread(target=read_output, args=(allocation_process,), daemon=True).start()
        print("Allocation_check.py started successfully")
    except Exception as e:
        print(f"Error starting Allocation_check.py: {e}")
        raise
        


# Function to stop the execution of the external script
def stop_allocation_check():
    global allocation_process
    if allocation_process and allocation_process.poll() is None:
        allocation_process.terminate()
        allocation_process = None



@app.callback(
    [Output('interval-component-script', 'disabled'),
     Output('start-message', 'children')],
    [Input('initialise-button', 'n_clicks'),
     Input('start-button', 'n_clicks'),
     Input('stop-button', 'n_clicks')],
    [State('interval-component-script', 'disabled')]
)
def control_allocation_check(initialise_clicks, start_clicks, stop_clicks, interval_disabled):
    ctx = dash.callback_context
    if not ctx.triggered:
        return interval_disabled, None
    
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]
    message = ""
    
    if triggered_id == 'initialise-button' and initialise_clicks:
        try:
            start_allocation_check("Initial")
            interval_disabled = False
            message = "Initialization process started."
        except Exception as e:
            message = f"Error starting initialization process: {str(e)}"
    elif triggered_id == 'start-button' and start_clicks:
        try:
            start_allocation_check("Start")
            interval_disabled = False
            message = "Program started successfully."
        except Exception as e:
            message = f"Error starting program: {str(e)}"
    elif triggered_id == 'stop-button' and stop_clicks:
        try:
            stop_allocation_check()
            interval_disabled = True
            message = "Program stopped."
        except Exception as e:
            message = f"Error stopping program: {str(e)}"
    print(message)
    return interval_disabled, message




def fetch_latest_completed_time():
    # Establish the database connection
    conn = psycopg2.connect(
        dbname="ProductDetails",
        user="PUser12",
        password="PSQL@123",
        host="localhost",
        port="5432"
    )
    cursor = conn.cursor()
    
    try:
        # Fetch the latest 'End Time' from the 'prodet' table where Status is 'Completed'
        query = sql.SQL('SELECT MAX("End Time") FROM {schema}.{table} WHERE "Status" = %s').format(
            schema=sql.Identifier('public'),
            table=sql.Identifier('prodet')
        )
        cursor.execute(query, ('Completed',))
        latest_end_time = cursor.fetchone()[0]

        # If there is a completed product, return its end time
        if latest_end_time:
            return latest_end_time
        else:
            return None
    except Exception as e:
        print(f"Error fetching latest completed time: {e}")
        return None
    finally:
        cursor.close()
        conn.close()
# Function to fetch data from the database
def fetch_data_runtime():
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        query = '''SELECT * FROM public."RunTime";'''
        with conn.cursor() as cursor:
            cursor.execute(query)
            run_time = cursor.fetchone()[0]
            #print(run_time)
            if run_time is None:
                run_time1 = 0  # Default value if no run_time is found
            else:
                run_time1 = float(run_time) 
            
            conn.commit()

        conn.close()
        return run_time1
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        
# Assume this is your global start_time initialized somewhere in your app
#Dash_time = datetime.now().replace(hour=9, minute=0, second=0, microsecond=0)  # Example start time
#Dash_time = datetime.now()
# Function to fetch data from the database
def update_data_runtime():
    try:
        conn = psycopg2.connect(
            dbname=db_name,
            user=db_username,
            password=db_password,
            host=db_host,
            port=db_port
        )
        # Set the runtime data to NULL
        update_query = '''UPDATE public."RunTime" SET "Run_time" = NULL;'''
            
        with conn.cursor() as cursor:
            cursor.execute(update_query)
            
            
            
            conn.commit()

        conn.close()
        
        
    except Exception as e:
        print(f"Error updating data: {e}")
        
# Callback to update the live clock and date
@app.callback(
    Output('live-clock', 'children'),
    Output('current-date', 'children'),
    Output('current-day', 'children'),
    Input('interval-component-clock', 'n_intervals')
)
def update_clock(n):
    global Dash_time
    # Initialize Dash_time if not already initialized
    if Dash_time is None:
        Dash_time = datetime.now()
    run_time=fetch_data_runtime()
    #print(run_time)
    if run_time!=None:

        Dash_time += timedelta(minutes=run_time)
        current_time = Dash_time.strftime('%H:%M:%S')
    # Check if time has wrapped around midnight
        if Dash_time.hour == 0 and Dash_time.minute < 5:
            Dash_time += timedelta(days=1)  # Increment date by 1 day
    update_data_runtime()
    
    current_date = Dash_time.strftime('%d-%m-%Y')
    current_day = Dash_time.strftime('%A')
    return current_time, current_date, current_day


@app.callback(
    Output('main-graph', 'figure'),
    [Input('plot-dropdown', 'value'), Input('interval-component-data', 'n_intervals')]
)
def update_graph(selected_plot,n):
    df = fetch_data()
    if df.empty:
        return px.line(title='No Data Available')

    # Process the DataFrame for each plot type
    if selected_plot=="Gantt Chart":
        # Convert 'Start Time' and 'End Time' columns to datetime
        df['Start Time'] = pd.to_datetime(df['Start Time'])
        df['End Time'] = pd.to_datetime(df['End Time'])
        print("Data after datetime conversion:")
        #print(df)
        
        # Calculate the duration (difference) between start and end times
        df['Duration'] = df['End Time'] - df['Start Time']
        
        # Prepare data for 2D Gantt chart
        df['Start Time'] = df['Start Time'].dt.strftime("%Y-%m-%d %H:%M:%S")
        df['End Time'] = df['End Time'].dt.strftime("%Y-%m-%d %H:%M:%S")

        # Define specific colors for each component
        color_discrete_map = {
            'C1': 'red',
            'C2': 'blue',
            'C3': 'green',
            'C4': 'orange',
            'C5': 'purple',
            # Add more components and colors as needed
        }
        
        fig = px.timeline(df, x_start='Start Time', x_end='End Time', y='Product Name', color='Components', 
                        title='Real-Time 2D Gantt Chart', labels={'Components': 'Component'}, 
                        hover_data={'Duration': '|%H:%M:%S'}, color_discrete_map=color_discrete_map)
        
        fig.update_layout(xaxis_title="Time", yaxis_title="Products")
        
        # Add machine IDs as text inside the rectangles
        for index, row in df.iterrows():
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
                    font=dict(color='black', size=9),
                    align='center',
                    xanchor='center',
                    yanchor='middle'
                )
    elif selected_plot == "Utilization":
        df['Time Diff'] = df['Time Diff'].apply(time_to_timedelta2)
        df['Utilization'] = df['Time Diff'].apply(calculate_utilization)
        #print(df)
        df['Utilization %'] = (df['Utilization'] / 420) * 100
        fig = px.bar(df, x='Machine Number', y='Utilization %',
                     labels={'Utilization %': 'Utilization (%)', 'Machine Number': 'Machine'},
                     title='Utilization Percentage for Each Machine')
    elif selected_plot == "Time Taken by each Machine":
        df['Time Diff'] = df['Time Diff'].apply(time_to_timedelta2)
        total_running_time = df.groupby('Machine Number')['Time Diff'].sum().reset_index()
        y_ticks = pd.to_timedelta(range(0, int(total_running_time['Time Diff'].max().total_seconds()) + 1, 30), unit='s')
        fig = px.bar(total_running_time, x='Machine Number', y='Time Diff',
                     labels={'Time Diff': 'Total Running Time (hh:mm:ss)', 'Machine Number': 'Machine'},
                     title='Total Running Time for Each Machine')
        fig.update_layout(
            yaxis=dict(
                tickmode='array',
                tickvals=y_ticks,
                ticktext=[str(td)[7:] for td in y_ticks]
            )
        )
    elif selected_plot == "Time taken by each product":
        df['Time Diff'] = df['Time Diff'].apply(time_to_timedelta2)
        total_running_time_component = df.groupby(['Product Name', 'Components'])['Time Diff'].sum().reset_index()
        total_running_time_component['Product_Component'] = total_running_time_component['Product Name'] + ' - ' + total_running_time_component['Components']
        max_seconds = int(total_running_time_component['Time Diff'].max().total_seconds())
        y_ticks = pd.to_timedelta(range(0, max_seconds + 1, 30), unit='s')
        fig = px.bar(total_running_time_component, x='Product_Component', y='Time Diff',
                     labels={'Time Diff': 'Total Running Time (hh:mm:ss)', 'Product_Component': 'Product - Component'},
                     title='Total Running Time for Each Product and Component')
        fig.update_layout(
            yaxis=dict(
                tickmode='array',
                tickvals=y_ticks,
                ticktext=[str(td)[7:] for td in y_ticks]
            ),
            xaxis_tickvals=total_running_time_component['Product_Component'],
            xaxis_ticktext=[f"{p.split(' - ')[0]}\n{p.split(' - ')[1]}" for p in total_running_time_component['Product_Component']]
        )
    elif selected_plot == "Wait Time":
        df['Wait Time'] = df['Wait Time'].apply(time_to_timedelta2)
        total_wait_time_component = df.groupby(['Product Name', 'Components'])['Wait Time'].sum().reset_index()
        total_wait_time_component['Product_Component'] = total_wait_time_component['Product Name'] + ' - ' + total_wait_time_component['Components']
        max_seconds = int(total_wait_time_component['Wait Time'].max().total_seconds())
        y_ticks = pd.to_timedelta(range(0, max_seconds + 1, 30), unit='s')
        fig = px.bar(total_wait_time_component, x='Product_Component', y='Wait Time',
                     labels={'Wait Time': 'Total Wait Time (hh:mm:ss)', 'Product_Component': 'Product - Component'},
                     title='Total Wait Time for Each Product and Component')
        fig.update_layout(
            yaxis=dict(
                tickmode='array',
                tickvals=y_ticks,
                ticktext=[str(td)[7:] for td in y_ticks]
            ),
            xaxis_tickvals=total_wait_time_component['Product_Component'],
            xaxis_ticktext=[f"{p.split(' - ')[0]}\n{p.split(' - ')[1]}" for p in total_wait_time_component['Product_Component']]
        )
    elif selected_plot == "Idle Time":
        df['Idle Time'] = df['Idle Time'].apply(time_to_timedelta2)
        total_ideal_time = df.groupby('Machine Number')['Idle Time'].sum().reset_index()
        y_ticks_1 = pd.to_timedelta(range(0, int(total_ideal_time['Idle Time'].max().total_seconds()) + 1, 7200), unit='s')
        fig = px.bar(total_ideal_time, x='Machine Number', y='Idle Time',
                     labels={'Idle Time': 'Total Idle Time (hh:mm:ss)', 'Machine Number': 'Machine'},
                     title='Total Idle Time for Each Machine')
        fig.update_layout(
            yaxis=dict(
                tickmode='array',
                tickvals=y_ticks_1,
                ticktext=[str(td)[7:] for td in y_ticks_1],
                tickformat='%H:%M:%S'
            )
        )
    elif selected_plot == "Product Components Status":
        df['Status'] = df['Status'].apply(lambda x: str(x).strip() if x is not None else '')
        status_colors = {
            "InProgress_Outsource": "orange",
            "InProgress_In House": "red",
            "Completed_In House": "green",
            "Completed_Outsource": "blue",
        }
        fig = go.Figure()

        for product in df['Product Name'].unique():
            product_data = df[df['Product Name'] == product]
            for component in product_data['Components'].unique():
                component_data = product_data[product_data['Components'] == component]
                status = component_data['Status'].values[0]
                process_type = component_data['Process Type'].values[0]
                machine_number = component_data['Machine Number'].values[0]
                
                key = f"{status}_{process_type}"
                color = status_colors.get(key, "grey")
                fig.add_trace(go.Scatter(
                    x=[product],
                    y=[component],
                    mode='markers+text',
                    marker=dict(
                        color=color,
                        size=30,
                        symbol='square'
                    ),
                    text=[machine_number],
                    textposition='middle center',
                    name=f'{product} - {component}',
                    legendgroup=key,
                    showlegend=False
                ))

        # Create legend items manually, ensuring only 4 specific entries
        custom_legend_names = {
            "InProgress_Outsource": "Component Out for Outsource",
            "Completed_Outsource": "Component Back From Outsource",
            "InProgress_In House": "Component InProgress Inhouse",
            "Completed_In House": "Component Completed Inhouse"
        }

        for status_key, color in status_colors.items():
            legend_name = custom_legend_names.get(status_key, status_key.replace("_", " and "))
            fig.add_trace(go.Scatter(
                x=[None], y=[None],
                mode='markers',
                marker=dict(
                    color=color,
                    size=10,
                    symbol='square'
                ),
                legendgroup=status_key,
                showlegend=True,
                name=legend_name
            ))

        fig.update_layout(
            title='Status of Each Product Component',
            xaxis_title='Product',
            yaxis_title='Component',
            xaxis=dict(tickmode='array', tickvals=df['Product Name'].unique()),
            yaxis=dict(tickmode='array', tickvals=df['Components'].unique()),
            legend_title_text='Status and Process Type'
        )
    elif selected_plot=="Remaining Time":
        product_times = {}
            
        for product in df['Product Name'].unique():
            product_df = df[df['Product Name'] == product]
            
            total_time = product_df['Run Time (min/1000)'].sum()
            remaining_time = product_df[product_df['Status'] != 'Completed']['Run Time (min/1000)'].sum()
            
            product_times[product] = {
                'Total Time': total_time,
                'Remaining Time': remaining_time
            }

        time_df=pd.DataFrame(product_times).T.reset_index().rename(columns={'index': 'Product Name'})
        #print(time_df)


        # Calculate the completed time
        time_df['Completed Time'] = time_df['Total Time'] - time_df['Remaining Time']

        # Create a stacked horizontal bar chart
        fig = go.Figure()

        # Add trace for Completed Time
        fig.add_trace(go.Bar(
            y=time_df['Product Name'],
            x=time_df['Completed Time'],
            orientation='h',
            name='Completed Time',
            marker=dict(color='green'),
            text=time_df['Completed Time'],
            textposition='inside',
        ))

        # Add trace for Remaining Time
        fig.add_trace(go.Bar(
            y=time_df['Product Name'],
            x=time_df['Remaining Time'],
            orientation='h',
            name='Remaining Time',
            marker=dict(color='red'),
            text=time_df['Remaining Time'],
            textposition='inside',
        ))

        # Update layout
        fig.update_layout(
            barmode='stack',
            title='Total and Remaining Time for Each Product',
            xaxis_title='Time (min)',
            yaxis_title='Product Name',
            yaxis=dict(automargin=True),
            legend=dict(
                orientation='h',
                yanchor='bottom',
                y=1.02,
                xanchor='right',
                x=1
            ),
            margin=dict(l=0, r=0, t=50, b=0)  # Adjust margin as needed
        )

    return fig

if __name__ == '__main__':
    

    app.run_server(debug=True)
