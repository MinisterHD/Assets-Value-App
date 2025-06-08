import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import Dash, html, dcc, Input, Output, callback, dash_table, State
from dash.exceptions import PreventUpdate

import plotly.express as px
import plotly.graph_objects as go

# --- Database Configuration ---
DB_CONFIG = {
    'host': 'host.docker.internal',
    'database': 'assets_db',
    'user': 'postgres',
    'password': 'admin',
    'port': '5432'
}


def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(**DB_CONFIG)


# --- Database Helper Functions (Optimized for Scalability) ---

def get_assets(search_term=None, asset_type=None, page_current=0, page_size=15):
    """
    Fetch a paginated list of assets with their latest prices.
    Supports filtering by search term and asset type.
    """
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    offset = page_current * page_size

    params = []
    where_clauses = []

    # Base query to get the latest price for each asset
    query = """
            SELECT DISTINCT \
            ON (a.id)
                a.id, a.asset_name, a.asset_name_en, a.asset_type,
                ph.price as current_price, ph.recorded_at as last_updated
            FROM assets a
                LEFT JOIN price_history ph \
            ON a.id = ph.asset_id \
            """

    # Dynamically build WHERE clauses for filtering
    if search_term:
        where_clauses.append("(LOWER(a.asset_name) LIKE LOWER(%s) OR LOWER(a.asset_name_en) LIKE LOWER(%s))")
        params.extend([f'%{search_term}%', f'%{search_term}%'])
    if asset_type:
        where_clauses.append("a.asset_type = %s")
        params.append(asset_type)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    query += " ORDER BY a.id, ph.recorded_at DESC LIMIT %s OFFSET %s"
    params.extend([page_size, offset])

    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def get_total_asset_count(search_term=None, asset_type=None):
    """Get the total count of assets matching the filter criteria."""
    conn = get_db_connection()
    cursor = conn.cursor()

    params = []
    where_clauses = []

    query = "SELECT COUNT(*) FROM assets a"

    if search_term:
        where_clauses.append("(LOWER(a.asset_name) LIKE LOWER(%s) OR LOWER(a.asset_name_en) LIKE LOWER(%s))")
        params.extend([f'%{search_term}%', f'%{search_term}%'])
    if asset_type:
        where_clauses.append("a.asset_type = %s")
        params.append(asset_type)

    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)

    cursor.execute(query, tuple(params))
    count = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return count


def get_price_history(asset_id, days=30):
    """Get price history for a specific asset over a given number of days."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    start_date = datetime.now() - timedelta(days=days)

    query = """
            SELECT price, recorded_at
            FROM price_history
            WHERE asset_id = %s \
              AND recorded_at >= %s
            ORDER BY recorded_at ASC \
            """
    cursor.execute(query, (asset_id, start_date))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def get_asset_details_by_ids(asset_ids):
    """Fetch the latest details for a specific list of asset IDs."""
    if not asset_ids:
        return []

    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    query = """
            SELECT DISTINCT \
            ON (a.id)
                a.id, a.asset_name, a.asset_name_en, a.asset_type,
                ph.price as current_price
            FROM assets a
                LEFT JOIN price_history ph \
            ON a.id = ph.asset_id
            WHERE a.id = ANY (%s)
            ORDER BY a.id, ph.recorded_at DESC \
            """
    cursor.execute(query, (asset_ids,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


# --- App Initialization ---
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
           suppress_callback_exceptions=True)
app.title = "Asset Portfolio Dashboard"

# --- Reusable Components & Styles ---
SEARCH_CARD_STYLE = {
    "padding": "2rem",
    "box-shadow": "0 4px 6px rgba(0,0,0,0.1)",
    "border-radius": "10px",
    "background-color": "#ffffff"
}

# --- App Layout ---
app.layout = dbc.Container([
    dcc.Store(id='portfolio-store', storage_type='session', data={}),
    html.Div(id='toast-container', style={"position": "fixed", "top": 20, "right": 20, "zIndex": 10}),

    dbc.Row(dbc.Col(html.H1("مدیریت سبد دارایی", className="text-center my-4 text-primary"), width=12)),

    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardBody([
                    html.H4("Search & Filter Assets", className="card-title"),
                    dbc.Row([
                        dbc.Col(dcc.Input(id='search-input', type='text', placeholder='Search by asset name...',
                                          className="w-100", debounce=True), md=5),
                        dbc.Col(dcc.Dropdown(
                            id='category-filter-dropdown',
                            options=[
                                {'label': 'All Categories', 'value': ''},
                                {'label': 'Currency', 'value': 'Currency'},
                                {'label': '18 Gold', 'value': 'Commodity'},
                                {'label': 'Iranian Stock Exchange', 'value': 'Iranian Stock Exchange'},
                                {'label': 'Crypto Currency', 'value': 'Crypto Currency'}
                            ],
                            value='', placeholder="Filter by category...",
                        ), md=5),
                        dbc.Col(html.Button(["Search ", html.I(className="fa fa-search ml-2")], id='search-button',
                                            n_clicks=0, className="w-100 btn-primary"), md=2),
                    ], className="align-items-center")
                ])
            ], body=True, style=SEARCH_CARD_STYLE)
        )
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            dbc.Card([
                dbc.Spinner(id="search-results-spinner", children=[
                    dash_table.DataTable(
                        id='assets-table',
                        columns=[
                            {'name': 'Asset Name', 'id': 'Asset Name'},
                            {'name': 'English Name', 'id': 'English Name'},
                            {'name': 'Type', 'id': 'Type'},
                            {'name': 'Current Price', 'id': 'Current Price'},
                        ],
                        data=[],
                        page_current=0,
                        page_size=15,
                        page_action='native',
                        row_selectable='single',
                        style_cell={'textAlign': 'left', 'padding': '10px', 'fontFamily': 'sans-serif'},
                        style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                        style_data={'border': '1px solid #dee2e6'},
                        style_data_conditional=[{'if': {'row_index': 'odd'}, 'backgroundColor': '#fcfcfc'}],
                    ),
                    html.Div(id='asset-interaction-controls', className="mt-3")  # Placeholder for buttons
                ])
            ], body=True, style=SEARCH_CARD_STYLE)
        ], width=12, lg=7, className="mb-4"),
        dbc.Col([
            dbc.Card(dbc.Spinner(id="price-history-spinner", children=[
                html.Div(id='price-history-container', children=[
                    html.H4("Price History", className="card-title"),
                    html.P("Select an asset from the table and click 'Show History' to see its price chart.",
                           className="text-muted"),
                    dcc.Graph(id='price-history-chart')
                ])
            ]), body=True, style=SEARCH_CARD_STYLE)
        ], width=12, lg=5, className="mb-4")
    ]),

    dbc.Row([
        dbc.Col(
            dbc.Card([
                dbc.CardBody([
                    html.H4("Your Portfolio", className="card-title"),
                    dbc.Row([
                        dbc.Col(id='portfolio-summary-container', width=12, lg=7),
                        dbc.Col(dcc.Graph(id='portfolio-pie-chart'), width=12, lg=5)
                    ])
                ])
            ], body=True, style=SEARCH_CARD_STYLE)
        )
    ], className="mb-5"),
], fluid=True, className="bg-light p-4")


# --- Callbacks ---

@callback(
    [Output('assets-table', 'data'),
     Output('assets-table', 'page_count')],
    [Input('search-button', 'n_clicks'),
     Input('category-filter-dropdown', 'value'),
     Input('assets-table', 'page_current'),
     Input('assets-table', 'page_size')],
    [State('search-input', 'value')]
)
def update_assets_table(n_clicks, asset_type, page_current, page_size, search_term):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else 'initial_load'

    if triggered_id in ['search-button', 'category-filter-dropdown']:
        page_current = 0

    total_assets = get_total_asset_count(search_term, asset_type)
    assets = get_assets(search_term, asset_type, page_current, page_size)
    page_count = -(-total_assets // page_size) if total_assets > 0 else 1

    if not assets:
        return [], 0

    table_data = [{
        'id': asset['id'],
        'Asset Name': asset['asset_name'],
        'English Name': asset['asset_name_en'] or '-',
        'Type': asset['asset_type'] or '-',
        'Current Price': f"{asset['current_price']:,.0f}" if asset.get('current_price') else 'N/A',
    } for asset in assets]

    return table_data, page_count


@callback(
    Output('asset-interaction-controls', 'children'),
    Input('assets-table', 'selected_rows'),
    State('assets-table', 'data')
)
def update_interaction_controls(selected_rows, table_data):
    if not selected_rows:
        return dbc.Alert("Select an asset from the table to interact.", color="info", className="mt-3")

    selected_row_data = table_data[selected_rows[0]]
    asset_name = selected_row_data['Asset Name']

    # Hidden div to store the selected asset's ID
    hidden_asset_id = html.Div(selected_row_data['id'], id='selected-asset-id', style={'display': 'none'})

    return html.Div([
        hidden_asset_id,
        dbc.Card([
            dbc.CardBody([
                html.H5(f"Manage '{asset_name}'", className="card-title"),
                dbc.Row([
                    dbc.Col(dcc.Input(id='add-quantity-input', type='number', placeholder='Enter quantity...', min=0,
                                      className="w-100"), lg=6),
                    dbc.Col(html.Button(["Add/Update Portfolio ", html.I(className="fa fa-plus-circle ml-2")],
                                        id='add-portfolio-button', n_clicks=0, className="w-100 btn-success"), lg=6),
                ], className="mb-3 align-items-center"),
                dbc.Row([
                    dbc.Col(html.Button(["Show Price History ", html.I(className="fa fa-chart-line ml-2")],
                                        id='show-history-button', n_clicks=0, className="w-100 btn-info"), lg=12),
                ])
            ])
        ])
    ])


@callback(
    [Output('portfolio-store', 'data'),
     Output('toast-container', 'children')],
    Input('add-portfolio-button', 'n_clicks'),
    [State('selected-asset-id', 'children'),
     State('add-quantity-input', 'value'),
     State('portfolio-store', 'data')],
    prevent_initial_call=True
)
def update_portfolio_store(n_clicks, asset_id, quantity, current_portfolio):
    if not asset_id or quantity is None:
        raise PreventUpdate

    try:
        quantity_float = float(quantity)
        if quantity_float >= 0:
            current_portfolio[str(asset_id)] = quantity_float
        else:  # Handle negative input
            raise PreventUpdate
    except (ValueError, TypeError):
        raise PreventUpdate

    toast = dbc.Toast(
        f"Portfolio updated for asset ID {asset_id}.",
        header="Success",
        icon="success",
        duration=3000,
        is_open=True,
    )
    return current_portfolio, toast


@callback(
    [Output('portfolio-summary-container', 'children'),
     Output('portfolio-pie-chart', 'figure')],
    Input('portfolio-store', 'data')
)
def update_portfolio_display(portfolio_data):
    if not portfolio_data:
        return html.Div("Your portfolio is empty. Add assets from the table above.",
                        className="text-center text-muted p-4"), {}

    asset_ids = [int(k) for k, v in portfolio_data.items() if float(v) > 0]
    if not asset_ids:
        return html.Div("Your portfolio is empty. Add assets with a quantity greater than 0.",
                        className="text-center text-muted p-4"), {}

    asset_details = get_asset_details_by_ids(asset_ids)

    if not asset_details:
        return html.Div("Could not fetch details for portfolio assets.", className="text-danger p-4"), {}

    portfolio_items = []
    total_value = 0
    for asset in asset_details:
        quantity = portfolio_data.get(str(asset['id']), 0)
        price = asset.get('current_price', 0) or 0
        value = quantity * float(price)
        total_value += value
        portfolio_items.append({
            'Asset': asset['asset_name'],
            'Type': asset['asset_type'],
            'Quantity': f"{quantity:,.2f}",
            'Price': f"{float(price):,.0f}",
            'Total Value': f"{value:,.0f}",
        })

    summary_df = pd.DataFrame(portfolio_items)

    summary_table = dash_table.DataTable(
        columns=[{'name': i, 'id': i} for i in summary_df.columns],
        data=summary_df.to_dict('records'),
        style_cell={'textAlign': 'left', 'padding': '8px'},
        style_header={'backgroundColor': '#e9ecef', 'fontWeight': 'bold'},
    )

    pie_fig = px.pie(
        summary_df,
        values=[float(str(v).replace(',', '')) for v in summary_df['Total Value']],
        names='Asset',
        title=f"Portfolio Distribution",
        hole=0.3,
        color_discrete_sequence=px.colors.sequential.Agsunset
    )
    pie_fig.update_traces(textposition='inside', textinfo='percent+label',
                          marker=dict(line=dict(color='#000000', width=1)))

    summary_section = html.Div([
        html.H5(f"Total Portfolio Value: {total_value:,.0f}", className="text-success font-weight-bold mb-3"),
        summary_table
    ])

    return summary_section, pie_fig


@callback(
    Output('price-history-container', 'children'),
    Input('show-history-button', 'n_clicks'),
    State('selected-asset-id', 'children'),
    prevent_initial_call=True
)
def update_price_history_chart(n_clicks, asset_id):
    if not asset_id:
        return html.Div("Please select an asset from the table first.", className="text-warning text-center p-4")

    # We need the asset name, which isn't stored. We could fetch it or redesign.
    # For now, let's just use the ID. A better solution would be to store name/id in a dcc.Store.
    history = get_price_history(int(asset_id), days=30)

    if not history:
        return html.Div(f"No price history available for Asset ID {asset_id}.", className="text-muted text-center p-4")

    df = pd.DataFrame(history)
    df['price'] = pd.to_numeric(df['price'])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df['recorded_at'], y=df['price'], mode='lines+markers',
        line=dict(color='#007bff', width=2),
        marker=dict(size=5, symbol='circle-open')
    ))
    fig.update_layout(
        title=f"Price History: Asset ID {asset_id}",
        xaxis_title="Date",
        yaxis_title="Price",
        hovermode='x unified',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color="#333")
    )

    current_price = df['price'].iloc[-1]
    avg_price = df['price'].mean()
    high_price = df['price'].max()
    low_price = df['price'].min()

    stats_card = dbc.Card(dbc.CardBody([
        html.H5(f"30-Day Analysis: Asset ID {asset_id}", className="card-title"),
        html.P(f"Current Price: {current_price:,.0f}", className="mb-1"),
        html.P(f"30-Day Avg: {avg_price:,.0f}", className="mb-1"),
        html.P(f"30-Day High: {high_price:,.0f}", className="mb-1"),
        html.P(f"30-Day Low: {low_price:,.0f}", className="mb-1"),
    ]), className="mt-3")

    return html.Div([
        dcc.Graph(figure=fig),
        stats_card
    ])


# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True)
