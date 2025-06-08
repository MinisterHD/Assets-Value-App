import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta

import dash
from dash import Dash, html, dcc, Input, Output, State, dash_table
from dash.exceptions import PreventUpdate
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

import plotly.express as px
import plotly.graph_objects as go

# --- Database Configuration ---
# Make sure your database is accessible. Using localhost for local development.
DB_CONFIG = {
    'host': 'localhost',  # Or 'host.docker.internal' if running in Docker
    'database': 'assets_db',
    'user': 'postgres',
    'password': 'admin',
    'port': '5432'
}


def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.OperationalError as e:
        print(f"Database connection failed: {e}")
        return None


# --- Database Helper Functions (largely unchanged) ---

def get_assets(search_term='', categories=None):
    """Fetches a list of all assets, optionally filtered by a search term and categories."""
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = "SELECT DISTINCT ON (a.id) a.id, a.asset_name, a.asset_name_en, a.asset_type FROM assets a"
    conditions, params = [], []
    if search_term:
        conditions.append("(LOWER(a.asset_name) LIKE LOWER(%s) OR LOWER(a.asset_name_en) LIKE LOWER(%s))")
        params.extend([f'%{search_term}%', f'%{search_term}%'])
    if categories:
        conditions.append("a.asset_type = ANY(%s)")
        params.append(categories)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    cursor.execute(query, tuple(params))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return results


def get_assets_by_category(categories):
    """Fetches assets for dropdowns based on selected categories."""
    if not categories: return []
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = "SELECT id, asset_name FROM assets WHERE asset_type = ANY(%s) ORDER BY asset_name"
    cursor.execute(query, (categories,))
    assets = cursor.fetchall()
    cursor.close()
    conn.close()
    return [{'label': asset['asset_name'], 'value': str(asset['id'])} for asset in assets]


def get_batch_price_history(asset_ids, days=90):
    if not asset_ids: return pd.DataFrame()
    conn = get_db_connection()
    if not conn: return pd.DataFrame()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    start_date = datetime.now() - timedelta(days=days)
    query = """
            SELECT a.id as asset_id, a.asset_name, ph.price, ph.recorded_at
            FROM price_history ph
                     JOIN assets a ON a.id = ph.asset_id
            WHERE ph.asset_id = ANY (%s) \
              AND ph.recorded_at >= %s
            ORDER BY ph.recorded_at ASC \
            """
    cursor.execute(query, (asset_ids, start_date))
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return pd.DataFrame(data)


def get_usd_price():
    conn = get_db_connection()
    if not conn: return 1.0  # Return a default/fallback value
    cursor = conn.cursor()
    query = """
            SELECT ph.price
            FROM price_history ph
                     JOIN assets a ON a.id = ph.asset_id
            WHERE a.asset_name_en = 'USD'
            ORDER BY ph.recorded_at DESC LIMIT 1 \
            """
    cursor.execute(query)
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return float(result[0]) if result else 1.0


def get_asset_details_by_ids(asset_ids):
    if not asset_ids: return []
    conn = get_db_connection()
    if not conn: return []
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    query = """
            SELECT DISTINCT \
            ON (a.id) a.id, a.asset_name, a.asset_name_en, a.asset_type, ph.price as current_price
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


# --- App Initialization and Data ---
app = Dash(__name__, external_stylesheets=[dbc.icons.FONT_AWESOME], suppress_callback_exceptions=True)
app.title = "Modern Asset Portfolio"
USD_TO_IRR_RATE = get_usd_price()
CATEGORY_OPTIONS = [
    {'label': 'Currency', 'value': 'Currency'},
    {'label': 'Commodity', 'value': 'Commodity'},
    {'label': 'Iranian Stock Exchange', 'value': 'Iranian Stock Exchange'},
    {'label': 'Crypto Currency', 'value': 'Crypto Currency'}
]


def create_empty_figure(text="No Data", theme="light"):
    """Creates a blank Plotly figure with a message, adapted for themes."""
    is_dark = theme == "dark"
    return go.Figure().update_layout(
        annotations=[dict(text=text, showarrow=False, font_size=20, font_color="gray" if is_dark else "black")],
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
    )


# --- App Layout ---
def create_layout():
    return dmc.MantineProvider(
        id="mantine-theme-provider",
        withCssVariables=True,
        withGlobalClasses=True,
        theme={"colorScheme": "dark"},  # Default to dark theme
        children=[
            dcc.Store(id='portfolio-store', storage_type='session', data={}),
            dcc.Store(id='theme-store', storage_type='local', data='dark'),
            dmc.Container([
                # -- Header --
                html.Div(
                    style={'padding': '1rem', 'borderBottom': '1px solid #373A40'},
                    children=[
                        dmc.Group(justify="space-between", children=[
                            dmc.Title("Modern Asset Portfolio", order=1,
                                      style={"background": "linear-gradient(to right, #6366f1, #06b6d4)",
                                             "-webkit-background-clip": "text",
                                             "-webkit-text-fill-color": "transparent"}),
                            dmc.ActionIcon(
                                id="theme-switch",
                                children=[html.I(className="fa-regular fa-sun")],
                                variant="outline", size="lg", radius="xl"
                            )
                        ])
                    ]),

                # -- Main Content --
                dmc.Space(h=20),
                dmc.Accordion(
                    value="portfolio",  # Open portfolio section by default
                    chevronPosition="left",
                    variant="separated",
                    children=[
                        # -- Section 1: Portfolio Summary & Management --
                        dmc.AccordionItem(
                            value="portfolio",
                            children=[
                                dmc.AccordionControl(
                                    "Your Portfolio & Asset Management",
                                    icon=html.I(className="fa-solid fa-chart-pie", style={"color": "#818cf8"})
                                ),
                                dmc.AccordionPanel([
                                    dmc.Grid([
                                        # Left side: Asset Explorer
                                        dmc.GridCol([
                                            dmc.Title("Asset Explorer", order=3, mb="md"),
                                            dmc.MultiSelect(id='asset-type-filter', data=CATEGORY_OPTIONS,
                                                            placeholder="Filter by type...", mb="sm"),
                                            dmc.TextInput(id='asset-search-input', placeholder="Search by name...",
                                                          leftSection=html.I(className="fa-solid fa-search"),
                                                          debounce=300, mb="md"),
                                            dmc.Alert(id='asset-selection-alert', title="Select an Asset", color="blue",
                                                      withCloseButton=True, hide=True),
                                            html.Div(id='asset-explorer-table'),
                                            html.Div(id='asset-interaction-controls', className="mt-4")
                                        ], span={'base': 12, 'md': 5}),

                                        # Right side: Portfolio Summary
                                        dmc.GridCol([
                                            dmc.Title("Portfolio Summary", order=3, mb="md"),
                                            dmc.Group(justify="space-between", mb="md", grow=True, children=[
                                                dmc.Text(id="portfolio-total-value", size="xl", fw=700, c="green"),
                                                dmc.SegmentedControl(
                                                    id='portfolio-currency-selector',
                                                    data=[{'label': 'IRR', 'value': 'IRR'},
                                                          {'label': 'USD', 'value': 'USD',
                                                           'disabled': not USD_TO_IRR_RATE or USD_TO_IRR_RATE == 1.0}],
                                                    value='IRR',
                                                )
                                            ]),
                                            html.Div(id='portfolio-summary-container'),
                                            dmc.SegmentedControl(
                                                id='portfolio-chart-type-selector',
                                                data=[{'label': 'Sunburst', 'value': 'sunburst'},
                                                      {'label': 'Treemap', 'value': 'treemap'}],
                                                value='sunburst', fullWidth=True, mt="md"
                                            ),
                                            dcc.Graph(id='portfolio-distribution-chart',
                                                      config={'displayModeBar': False})
                                        ], span={'base': 12, 'md': 7}),
                                    ], gutter="xl")
                                ])
                            ]
                        ),

                        # -- Section 2: Portfolio & Asset Performance --
                        dmc.AccordionItem(
                            value="performance",
                            children=[
                                dmc.AccordionControl(
                                    "Performance Analysis",
                                    icon=html.I(className="fa-solid fa-arrow-trend-up", style={"color": "#22d3ee"})
                                ),
                                dmc.AccordionPanel([
                                    dmc.Tabs(
                                        variant="outline",
                                        value="portfolio_perf",
                                        children=[
                                            dmc.TabsList([
                                                dmc.TabsTab("Portfolio Performance (30-Day)", value="portfolio_perf"),
                                                dmc.TabsTab("Comparative Asset Analysis (90-Day)",
                                                            value="compare_perf"),
                                            ]),
                                            dmc.TabsPanel(dcc.Graph(id='portfolio-performance-chart'),
                                                          value="portfolio_perf", pt="md"),
                                            dmc.TabsPanel([
                                                dmc.Grid([
                                                    dmc.GridCol(dmc.MultiSelect(id='comparison-category-selector',
                                                                                data=CATEGORY_OPTIONS,
                                                                                placeholder="1. Select categories..."),
                                                                span={'base': 12, 'sm': 4}),
                                                    dmc.GridCol(dmc.MultiSelect(id='comparison-asset-selector',
                                                                                placeholder="2. Select assets (2+)...",
                                                                                disabled=True),
                                                                span={'base': 12, 'sm': 8}),
                                                ], mb="md"),
                                                dmc.Group(justify="flex-end", mb="md", children=[
                                                    dmc.SegmentedControl(
                                                        id='comparison-chart-type-selector',
                                                        data=[{'label': 'Performance', 'value': 'performance'},
                                                              {'label': 'Correlation', 'value': 'correlation'},
                                                              {'label': 'Volatility', 'value': 'volatility'}],
                                                        value='performance'
                                                    ),
                                                    dmc.SegmentedControl(
                                                        id='comparison-currency-selector',
                                                        data=[{'label': 'IRR (M)', 'value': 'IRR'},
                                                              {'label': 'USD', 'value': 'USD',
                                                               'disabled': not USD_TO_IRR_RATE or USD_TO_IRR_RATE == 1.0}],
                                                        value='IRR'
                                                    ),
                                                ]),
                                                dcc.Graph(id='asset-comparison-chart')
                                            ], value="compare_perf", pt="md"),
                                        ]
                                    )
                                ])
                            ]
                        )
                    ]
                )
            ], fluid=True, p="md")
        ]
    )


app.layout = create_layout()


# --- Callbacks ---

# Theme switching callback
@app.callback(
    Output("mantine-theme-provider", "theme"),
    Output("theme-switch", "children"),
    Output("theme-store", "data"),
    Input("theme-switch", "n_clicks"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def switch_theme(n_clicks, current_theme):
    new_theme = "light" if current_theme == "dark" else "dark"
    icon = html.I(className="fa-regular fa-moon") if new_theme == "dark" else html.I(className="fa-regular fa-sun")
    return {"colorScheme": new_theme}, icon, new_theme


@app.callback(
    Output('asset-explorer-table', 'children'),
    Input('asset-search-input', 'value'),
    Input('asset-type-filter', 'value')
)
def update_asset_explorer(search_term, selected_types):
    assets = get_assets(search_term or '', selected_types)
    if not assets:
        return dmc.Text("No assets found.", ta="center", p="md")

    table = dash_table.DataTable(
        id='asset-table-interactive',
        columns=[
            {'name': 'Asset Name', 'id': 'asset_name', 'type': 'text'},
            {'name': 'English Name', 'id': 'asset_name_en', 'type': 'text'},
            {'name': 'Type', 'id': 'asset_type', 'type': 'text'},
        ],
        data=assets,
        row_selectable='single',
        page_size=10,
        style_as_list_view=True,
        style_header={'display': 'none'},
        style_cell={'textAlign': 'left', 'padding': '10px', 'border': 'none', 'backgroundColor': 'transparent'},
        style_data_conditional=[{
            'if': {'state': 'selected'},
            'backgroundColor': 'rgba(129, 140, 248, 0.2)',  # bg-indigo-300/20
            'border': 'none',
        }]
    )
    return table


@app.callback(
    Output('asset-interaction-controls', 'children'),
    Output('asset-selection-alert', 'hide'),
    Output('asset-selection-alert', 'children'),
    Input('asset-table-interactive', 'selected_rows'),
    State('asset-table-interactive', 'data'),
    State('portfolio-store', 'data')
)
def update_interaction_controls(selected_rows, table_data, portfolio):
    if not selected_rows:
        return None, True, ""

    if table_data is None:
        raise PreventUpdate

    asset = table_data[selected_rows[0]]
    asset_id = str(asset['id'])
    current_quantity = portfolio.get(asset_id, "")

    alert_text = f"Selected: {asset['asset_name']}. Current quantity in portfolio: {current_quantity or 0}"

    controls = [
        html.Div(asset['id'], id='selected-asset-id', style={'display': 'none'}),
        dmc.Group([
            dmc.NumberInput(
                id='add-quantity-input',
                label=f"Manage '{asset['asset_name']}'",
                placeholder='Enter quantity...',
                min=0,
                value=current_quantity,
                style={'flexGrow': 1}
            ),
            dmc.Button(
                "Update Portfolio",
                id='add-portfolio-button',
                leftSection=html.I(className="fa-solid fa-save"),
                variant="light",
                mt=25
            )
        ])
    ]
    return controls, False, alert_text


@app.callback(
    Output('portfolio-store', 'data', allow_duplicate=True),
    Input('add-portfolio-button', 'n_clicks'),
    State('selected-asset-id', 'children'),
    State('add-quantity-input', 'value'),
    State('portfolio-store', 'data'),
    prevent_initial_call=True
)
def update_portfolio_store(n_clicks, asset_id, quantity, portfolio):
    if not asset_id or quantity is None: raise PreventUpdate
    portfolio = portfolio or {}
    try:
        if float(quantity) > 0:
            portfolio[str(asset_id)] = float(quantity)
        elif str(asset_id) in portfolio:
            del portfolio[str(asset_id)]
    except (ValueError, TypeError):
        raise PreventUpdate
    return portfolio


@app.callback(
    [Output('portfolio-summary-container', 'children'),
     Output('portfolio-distribution-chart', 'figure'),
     Output('portfolio-total-value', 'children')],
    Input('portfolio-store', 'data'),
    Input('portfolio-chart-type-selector', 'value'),
    Input('portfolio-currency-selector', 'value'),
    Input('theme-store', 'data')
)
def update_portfolio_summary_and_dist(portfolio_data, chart_type, currency, theme):
    if not portfolio_data:
        empty_fig = create_empty_figure("Portfolio is empty", theme)
        return dmc.Text("Your portfolio is empty.", ta="center", p="xl"), empty_fig, "Total Value: 0"

    asset_ids = [int(k) for k, v in portfolio_data.items() if float(v) > 0]
    if not asset_ids:
        empty_fig = create_empty_figure("No assets with quantity", theme)
        return dmc.Text("Add assets with quantity > 0.", ta="center", p="xl"), empty_fig, "Total Value: 0"

    asset_details = get_asset_details_by_ids(asset_ids)
    if not asset_details:
        empty_fig = create_empty_figure("Error fetching data", theme)
        return dmc.Alert("Could not fetch asset details.", color="red"), empty_fig, "Total Value: -"

    portfolio_items, total_value_irr = [], 0
    for asset in asset_details:
        quantity = portfolio_data.get(str(asset['id']), 0)
        price_irr = float(asset.get('current_price', 0) or 0)
        value_irr = quantity * price_irr
        total_value_irr += value_irr
        portfolio_items.append({
            'Asset': asset['asset_name'], 'Type': asset['asset_type'], 'Quantity': quantity,
            'Price_IRR': price_irr, 'Total_Value_IRR': value_irr
        })
    if not portfolio_items:
        summary_df = pd.DataFrame()
    else:
        summary_df = pd.DataFrame(portfolio_items)

    total_value = total_value_irr
    if currency == 'USD' and USD_TO_IRR_RATE > 1:
        if not summary_df.empty:
            summary_df['Price'] = summary_df['Price_IRR'] / USD_TO_IRR_RATE
            summary_df['Total Value'] = summary_df['Total_Value_IRR'] / USD_TO_IRR_RATE
        total_value = total_value_irr / USD_TO_IRR_RATE
        num_format = "{:,.2f}"
    else:
        if not summary_df.empty:
            summary_df['Price'] = summary_df['Price_IRR']
            summary_df['Total Value'] = summary_df['Total_Value_IRR']
        num_format = "{:,.0f}"

    table_data = [
        html.Thead(html.Tr(
            [html.Th("Asset"), html.Th("Quantity"), html.Th(f"Price ({currency})"), html.Th(f"Value ({currency})")])),
        html.Tbody([
            html.Tr([
                html.Td(row['Asset']), html.Td(f"{row['Quantity']:,.2f}"),
                html.Td(num_format.format(row['Price'])), html.Td(num_format.format(row['Total Value']))
            ]) for i, row in summary_df.iterrows()
        ])
    ]
    summary_table = dmc.Table(children=table_data, striped=True, highlightOnHover=True, withTableBorder=True)

    chart_funcs = {'sunburst': px.sunburst, 'treemap': px.treemap}
    if summary_df.empty:
        dist_fig = create_empty_figure("No data for chart", theme)
    else:
        dist_fig = chart_funcs[chart_type](
            summary_df, path=['Type', 'Asset'], values='Total_Value_IRR',
            template='plotly_dark' if theme == 'dark' else 'plotly_white'
        )
        # FIX: Explicitly set font color for chart text.
        font_color = 'white' if theme == 'dark' else 'black'
        dist_fig.update_layout(
            margin=dict(t=10, l=10, r=10, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            font_color=font_color
        )

    return summary_table, dist_fig, f"Total Value: {num_format.format(total_value)} {currency}"


@app.callback(
    Output('portfolio-performance-chart', 'figure'),
    Input('portfolio-store', 'data'),
    Input('theme-store', 'data')
)
def update_portfolio_performance(portfolio_data, theme):
    if not portfolio_data: return create_empty_figure("No portfolio assets", theme)
    asset_ids = [int(k) for k, v in portfolio_data.items() if float(v) > 0]
    if not asset_ids: return create_empty_figure("No portfolio assets", theme)

    history_df = get_batch_price_history(asset_ids, days=30)
    if history_df.empty or len(history_df['recorded_at'].unique()) < 2:
        return create_empty_figure("Not enough price history", theme)

    history_df['price'] = pd.to_numeric(history_df['price'])

    # The variable name normalized_df is confusing, but the logic is correct.
    # It creates a pandas Series, which is then assigned to a new column.
    normalized_series = history_df.groupby('asset_name')['price'].transform(
        lambda x: (x / x.iloc[0]) * 100 if not x.empty and x.iloc[0] != 0 else x
    )
    history_df['normalized'] = normalized_series

    fig = px.line(history_df, x='recorded_at', y='normalized', color='asset_name',
                  template='plotly_dark' if theme == 'dark' else 'plotly_white')

    # FIX: Globally set font color for all chart text elements.
    font_color = 'white' if theme == 'dark' else 'black'
    fig.update_layout(
        title_text="Portfolio Performance (30-Day Normalized)",
        yaxis_title="Performance (Start = 100)",
        xaxis_title=None,
        font=dict(color=font_color),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        legend_title_text=''
    )
    return fig


@app.callback(
    [Output('comparison-asset-selector', 'data'), Output('comparison-asset-selector', 'disabled')],
    Input('comparison-category-selector', 'value')
)
def update_comparison_asset_dropdown(selected_categories):
    if not selected_categories:
        return [], True
    asset_options = get_assets_by_category(selected_categories)
    return asset_options, False


@app.callback(
    Output('asset-comparison-chart', 'figure'),
    Input('comparison-asset-selector', 'value'),
    Input('comparison-currency-selector', 'value'),
    Input('comparison-chart-type-selector', 'value'),
    Input('theme-store', 'data')
)
def update_asset_comparison_chart(selected_assets, currency, chart_type, theme):
    if not selected_assets or len(selected_assets) < 2:
        return create_empty_figure("Select 2+ assets to compare", theme)

    asset_ids_int = [int(asset_id) for asset_id in selected_assets]
    df = get_batch_price_history(asset_ids_int, days=90)

    if df.empty: return create_empty_figure("No historical data available", theme)

    df['price'] = pd.to_numeric(df['price'])
    if currency == 'USD' and USD_TO_IRR_RATE > 1:
        df['price'] /= USD_TO_IRR_RATE
    # Removed the division by 1,000,000 as it might not be universally desired
    # else:
    #     df['price'] /= 1_000_000

    template = 'plotly_dark' if theme == 'dark' else 'plotly_white'
    font_color = 'white' if theme == 'dark' else 'black'
    fig = go.Figure()

    if chart_type == 'performance':
        # FIX: Use the same proven normalization logic as the portfolio chart
        # This avoids the complexity and potential errors of using a pivot table for this view
        if df.empty or len(df['recorded_at'].unique()) < 2:
            return create_empty_figure("Not enough price history for comparison", theme)

        df['normalized'] = df.groupby('asset_name')['price'].transform(
            lambda x: (x / x.iloc[0] * 100) if not x.empty and x.iloc[0] != 0 else x
        )

        fig = px.line(df, x='recorded_at', y='normalized', color='asset_name',
                      title="Normalized Performance Comparison")
        fig.update_layout(yaxis_title="Performance (Start = 100)", xaxis_title=None)

    else:
        # For correlation and volatility, we still need the pivot table
        pivot_df = df.pivot_table(index='recorded_at', columns='asset_name', values='price')
        pivot_df.dropna(axis=1, how='all', inplace=True)
        if pivot_df.shape[1] < 2:
            return create_empty_figure("Need >1 asset with data for comparison", theme)

        if chart_type == 'correlation':
            returns_df = pivot_df.pct_change().dropna()
            if len(returns_df) < 1: return create_empty_figure("Not enough data for correlation", theme)
            corr_matrix = returns_df.corr()
            fig = px.imshow(corr_matrix, text_auto=True, aspect="auto", title="Price Correlation Heatmap",
                            color_continuous_scale='RdBu_r')

        elif chart_type == 'volatility':
            returns_df = pivot_df.pct_change().dropna()
            if len(returns_df) < 1: return create_empty_figure("Not enough data for volatility", theme)
            melted_returns = returns_df.melt(var_name='asset_name', value_name='daily_return')
            fig = px.box(melted_returns, x='asset_name', y='daily_return', title="Daily Return Volatility",
                         points="all")
            fig.update_yaxes(title="Daily % Change", zeroline=True, zerolinewidth=1)
            fig.update_xaxes(title=None)

    fig.update_layout(
        template=template,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color=font_color),
        legend_title_text=''
    )
    return fig


# --- Run the App ---
if __name__ == '__main__':
    app.run(debug=True)
