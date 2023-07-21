import streamlit as st
import pandas as pd
import websocket
import json
import keras
import requests
from sklearn import preprocessing
from sklearn.preprocessing import MinMaxScaler
import threading
import re

# Streamlit app title and description
st.title('Crypto Price Prediction & Trading Bot')
st.write('This is a simple crypto price prediction and trading bot app.')

# Load the trained machine learning model
# Input widget for selecting cryptocurrency and providing historical data
crypto_list = ['BTC', 'ETH', 'LTC']
symbol = 'BITSTAMP_SPOT_BTC_USD'
selected_crypto = st.selectbox('Select a cryptocurrency:', crypto_list)
url = "https://rest.coinapi.io/v1/ohlcv/BITSTAMP_SPOT_BTC_USD/history"
api_key = "EB519846-6527-4BAA-AA7D-FDD4E2CDF8E3"

@st.cache_data(ttl=86400)
def get_historical_data(symbol):
    headers = {"X-CoinAPI-Key": api_key}
    parameters = {
        "period_id": "1DAY",
        "time_start": "2011-01-01T00:00:00",
        "limit": 5000 # Maximum number of data points to retrieve
    }

    try:
        response = requests.get(url.format(symbol=symbol), headers=headers, params=parameters)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data)
        return df

    except requests.exceptions.RequestException as e:
        print("An error occurred during data retrieval:", str(e))
        return None

if 'df' not in st.session_state:
    st.session_state.df = pd.DataFrame()

# model = keras.models.load_model('price_prediction_btc.h5')
symbol = ""
if selected_crypto == "LTC":
    symbol = "BITSTAMP_SPOT_LTC_USD"
    st.session_state.df = get_historical_data(symbol)
    model = keras.models.load_model('price_prediction_ltc2.h5')
elif selected_crypto == "BTC":
    model = keras.models.load_model('price_prediction_btc1.h5')
    symbol = "BITSTAMP_SPOT_BTC_USD"
    st.session_state.df = get_historical_data(symbol)
elif selected_crypto == "ETH":
    model = keras.models.load_model('price_prediction_eth2.h5')
    symbol = "BITSTAMP_SPOT_ETH_USD"
    st.session_state.df = get_historical_data(symbol)

# df.set_index('Timestamp', inplace=True)

sma_period = 10
macd_fast_period = 12
macd_slow_period = 26
macd_signal_period = 9
def preprocess_data(data):
    data['Timestamp'] = pd.to_datetime(data['time_period_start'])
    data.set_index('Timestamp', inplace=True)

    # Normalize data
    scaler = MinMaxScaler()
    data['price_close'] = scaler.fit_transform(data['price_close'].values.reshape(-1, 1))
    
    # Load the latest 5 data points for prediction
    latest_data = data['price_close'][-30:]  # Get the last 5 days of data
    latest_data = latest_data.values.reshape(1, 30, 1)  # Reshape to three dimensions for LSTM input
    

    # Make predictions for the latest data points
    latest_predictions = model.predict(latest_data)

    # Denormalize the predictions
    latest_predictions = scaler.inverse_transform(latest_predictions)

    # Print the predictions for each da
    # Display the predictions
    st.write('Price Predictions for', selected_crypto)
    if selected_crypto == "BTC":
        st.write(latest_predictions[0][0])
    elif selected_crypto == "ETH":
        st.write(latest_predictions[0][0]/16.09)
    elif selected_crypto == "LTC":
        st.write(latest_predictions[0][0]/328)
preprocess_data(st.session_state.df)

# WebSocket connection variables for trading bot
endpoint = 'wss://fstream.binance.com/ws/'
ws = None
start_bot = st.button('Start Bot')
stop_bot = st.button('Stop Bot')
msg = json.dumps({
    "method": "SUBSCRIBE",
    "params": [f"{selected_crypto.lower()}usdt@kline_15m", f"{selected_crypto.lower()}usdt@kline_1m"],
    "id": 1
})
i=0
# Initialize session state variables
if 'trade_results' not in st.session_state:
    st.session_state.trade_results = {}
in_position = False
buy_price = 0.0
returns = {'15m': 0, '1m': 0}
stop_event = threading.Event()

def on_open(ws):
    ws.send(msg)

def on_message(ws, message):
    global df, in_position, buy_price,i
    out = json.loads(message)
    df = pd.DataFrame(out['k'], index=[pd.to_datetime(out['E'], unit='ms')])[['s', 'i', 'o', 'c']]
    df.loc[:, 'ret ' + df.i.values[0]] = float(df.c) / float(df.o) - 1
    returns[df.i.values[0]] = float(df.c) / float(df.o) - 1
    
    if not in_position and returns['15m'] < 0 and returns['1m'] > 0:
        buy_price = float(df.c)
        st.write('Bought')
        df.rename(columns={'s': 'Symbol', 'o': 'Open Price', 'c': 'Close Price', 'i': 'Interval'}, inplace=True)
        st.write(df)
        st.session_state.trade_results[f"Bought{i}"] = df
        in_position = True
        st.write('In position, checking for selling opportunities')
        i+=1

    if in_position:
        st.write('Target profit:', buy_price * 1.0002)
        st.write('Stop loss:', buy_price * 0.9998)

        if float(df.c) > buy_price * 1.0002:
            st.write('Target Profit reached - SELL')
            st.write('Profit:', float(df.c) - buy_price)
            profit = float(df.c) - buy_price
            in_position = False
            df.rename(columns={'s': 'Symbol', 'o': 'Open Price', 'c': 'Close Price', 'i': 'Interval'}, inplace=True)
            st.session_state.trade_results[f"SELL{i}"] = df
            st.session_state.trade_results[f"Profit{i}"] = profit
            i+=1
        elif float(df.c) < buy_price * 0.9998:
            st.write('Stop Loss reached - SELL')
            st.write('Loss:', float(df.c) - buy_price)
            loss = float(df.c) - buy_price
            in_position = False
            df.rename(columns={'s': 'Symbol', 'o': 'Open Price', 'c': 'Close Price', 'i': 'Interval'}, inplace=True)
            st.session_state.trade_results[f"SELL{i}"] = df
            st.session_state.trade_results[f"LOSS{i}"] = loss
            i+=1

    if stop_event.is_set():
        ws.close()
        return
def main():
    global ws
    ws = websocket.WebSocketApp(endpoint, on_message=on_message, on_open=on_open)
    ws.run_forever()

# Check if the bot should be started or stopped
if start_bot:
    msg = json.dumps({
        "method": "SUBSCRIBE",
        "params": [f"{selected_crypto.lower()}usdt@kline_15m", f"{selected_crypto.lower()}usdt@kline_1m"],
        "id": 1
    })
    with st.spinner('Started the trading bot...'):
        main()
    st.success("Trading bot started!")

if stop_bot:
    if ws:
        ws.close()
    st.success("Trading bot stopped!")
    st.info('return 1m means : Percentage return for last 1-minute interval and "return 15m"  for last 15-minute interval')
    st.info('These variables store the percentage returns, which indicate the percentage change in price during the given time intervals.')

    for i in st.session_state.trade_results:
        st.write(re.sub(r'\d+', '', i)," : ",st.session_state.trade_results[i])
