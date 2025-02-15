import os
import time
import logging
import traceback
import ccxt
import pandas as pd
from dotenv import load_dotenv
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.exceptions import NotFittedError
from datetime import datetime
import sys

# ============================
# Configuration and Setup
# ============================

# Load environment variables
load_dotenv()
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_API_SECRET = os.getenv("BINANCE_SECRET_KEY")

if not BINANCE_API_KEY or not BINANCE_API_SECRET:
    raise ValueError("API 키가 누락되었습니다. .env 파일을 확인하세요.")

LOG_DIR = "logs"
MODEL_DIR = "models"
MODEL_PATH = os.path.join(MODEL_DIR, 'ai_model.pkl')
SCALER_PATH = os.path.join(MODEL_DIR, 'scaler.pkl')
LABEL_ENCODER_PATH = os.path.join(MODEL_DIR, 'label_encoder.pkl')
TRADE_HISTORY_FILE = "trade_history.csv"
TRADE_INTERVAL = 60

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)

# Define constants for indicators
EMA_SHORT_PERIOD = 12
EMA_LONG_PERIOD = 26
MACD_SHORT_PERIOD = 12
MACD_LONG_PERIOD = 26
MACD_SIGNAL_PERIOD = 9
RSI_PERIOD = 14

# Setup logging
def setup_logger(name, log_file, level=logging.INFO):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)
    return logger

general_logger = setup_logger("general", os.path.join(LOG_DIR, "general_log.log"))
error_logger = setup_logger("error", os.path.join(LOG_DIR, "error_log.log"), level=logging.WARNING)

# ============================
# AIDecisionMaker 클래스
# ============================

class AIDecisionMaker:
    def __init__(self, model_path=MODEL_PATH, scaler_path=SCALER_PATH, label_encoder_path=LABEL_ENCODER_PATH):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.label_encoder_path = label_encoder_path
        self.model = None
        self.scaler = None
        self.label_encoder = None
        self.expected_input_size = None
        self.load_model()

    def load_model(self):
        try:
            self.model = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path) if os.path.exists(self.scaler_path) else StandardScaler()
            self.label_encoder = joblib.load(self.label_encoder_path) if os.path.exists(self.label_encoder_path) else LabelEncoder()
            self.expected_input_size = self.model.n_features_in_
            general_logger.info("AI 모델 및 관련 파일 로드 성공")
        except Exception as e:
            error_logger.error(f"모델 로드 오류: {e}")
            self.model = None

    def train_model(self, input_size=7):
        self.expected_input_size = input_size
        X = np.random.rand(100, self.expected_input_size)
        y = np.random.randint(0, 2, 100)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.label_encoder = LabelEncoder()
        y_encoded = self.label_encoder.fit_transform(y)

        self.model = RandomForestClassifier()
        self.model.fit(X_scaled, y_encoded)

        joblib.dump(self.model, self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        joblib.dump(self.label_encoder, self.label_encoder_path)
        general_logger.info("모델 및 관련 파일 저장 완료")

    def predict(self, indicators):
        if not self.model or not self.scaler or not self.label_encoder:
            error_logger.error("AI 모델, Scaler, 또는 Label Encoder가 로드되지 않았습니다.")
            return 'HOLD'

        try:
            feature_vector = list(indicators.values())
            input_size = len(feature_vector)

            # 입력 크기 확인 및 동적 조정
            if self.expected_input_size != input_size:
                general_logger.warning(f"입력 크기 불일치: {input_size} (예상: {self.expected_input_size}). None로 설정.")
                return 'HOLD'

            X = np.array(feature_vector).reshape(1, -1)
            X = self.scaler.transform(X) if self.scaler else X

            prediction_encoded = self.model.predict(X)[0]
            prediction = self.label_encoder.inverse_transform([prediction_encoded])[0]
            return prediction
        except Exception as e:
            error_logger.error(f"AI 예측 오류: {e}")
            return 'HOLD'

# ============================
# Main Execution
# ============================

if __name__ == "__main__":
    try:
        ai_decision_maker = AIDecisionMaker()

        # 테스트를 위한 예제 데이터
        sample_indicators = {
            'EMA_short': 1.2,
            'EMA_long': 1.1,
            'MACD': 0.5,
            'MACD_signal': 0.4,
            'RSI': 60,
            'Additional1': 0.3,
            'Additional2': 0.7
        }

        decision = ai_decision_maker.predict(sample_indicators)
        general_logger.info(f"AI의 결정: {decision}")
    except Exception as e:
        error_logger.critical(f"시스템 실행 중 치명적인 오류 발생: {e}")
        traceback.print_exc()

# ============================
# Binance API Wrapper
# ============================

class BinanceAPI:
    def __init__(self, api_key, api_secret):
        self.binance = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future'
            }
        })

    def fetch_balance_sync(self):
        try:
            return self.binance.fetch_balance()
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")  # 네트워크 오류는 WARNING으로
            return None
        except ccxt.ExchangeError as e:
            error_logger.error(f"잔고 가져오기 교환 오류: {e}")
            return None
        except Exception as e:
            error_logger.error(f"잔고 가져오기 예기치 않은 오류: {e}")
            return None

    def fetch_markets_sync(self):
        try:
            return self.binance.load_markets()
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")
            return None
        except ccxt.ExchangeError as e:
            error_logger.error(f"시장 정보 로드 교환 오류: {e}")
            return None
        except Exception as e:
            error_logger.error(f"시장 정보 로드 예기치 않은 오류: {e}")
            return None

    def fetch_ticker_sync(self, symbol):
        try:
            return self.binance.fetch_ticker(symbol)
        except ccxt.BadSymbol as e:
            error_logger.warning(f"{symbol} 잘못된 심볼: {e}")  # 잘못된 심볼은 WARNING
            return None
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")
            return None
        except ccxt.ExchangeError as e:
            error_logger.error(f"{symbol} 티커 가져오기 교환 오류: {e}")
            return None
        except Exception as e:
            error_logger.error(f"{symbol} 티커 가져오기 예기치 않은 오류: {e}")
            return None

    def fetch_historical_ohlcv_sync(self, symbol, timeframe='1h', limit=1000):
        try:
            ohlcv = self.binance.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except ccxt.BadSymbol as e:
            error_logger.warning(f"{symbol} 잘못된 심볼로 인한 OHLCV 데이터 오류: {e}")
            return None
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")
            return None
        except ccxt.ExchangeError as e:
            error_logger.error(f"{symbol}의 역사적 OHLCV 데이터 교환 오류: {e}")
            return None
        except Exception as e:
            error_logger.error(f"{symbol}의 역사적 OHLCV 데이터 예기치 않은 오류: {e}")
            return None

    def place_order_sync(self, symbol, side, amount, order_type='MARKET'):
        try:
            order = self.binance.create_order(symbol, order_type, side, amount)
            general_logger.info(f"주문 실행됨: {order}")
            return order
        except ccxt.InsufficientFunds as e:
            error_logger.error(f"{symbol} 주문 실행 자금 부족: {e}")
            return None
        except ccxt.BadSymbol as e:
            error_logger.warning(f"{symbol} 잘못된 심볼로 인한 주문 실행 오류: {e}")
            return None
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")
            return None
        except ccxt.ExchangeError as e:
            error_logger.error(f"{symbol} 주문 실행 교환 오류: {e}")
            return None
        except Exception as e:
            error_logger.error(f"{symbol} 주문 실행 예기치 않은 오류: {e}")
            return None

    def set_leverage(self, symbol, leverage):
        try:
            response = self.binance.fapiPrivate_post_leverage({
                'symbol': self.binance.market_id(symbol),
                'leverage': leverage
            })
            general_logger.info(f"{symbol} 레버리지 설정됨: {leverage}")
            return response
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")
            return None
        except ccxt.ExchangeError as e:
            error_logger.error(f"{symbol} 레버리지 설정 교환 오류: {e}")
            return None
        except Exception as e:
            error_logger.error(f"{symbol} 레버리지 설정 예기치 않은 오류: {e}")
            return None

    def fetch_minimum_trade_amount_sync(self, symbol):
        try:
            market = self.binance.market(symbol)
            return market['limits']['amount']['min']
        except ccxt.BadSymbol as e:
            error_logger.warning(f"{symbol} 잘못된 심볼로 인한 최소 거래 금액 오류: {e}")
            return MIN_TRADE_AMOUNT
        except ccxt.NetworkError as e:
            error_logger.warning(f"네트워크 오류: {e}")
            return MIN_TRADE_AMOUNT
        except ccxt.ExchangeError as e:
            error_logger.error(f"{symbol} 최소 거래 금액 교환 오류: {e}")
            return MIN_TRADE_AMOUNT
        except Exception as e:
            error_logger.error(f"{symbol} 최소 거래 금액 예기치 않은 오류: {e}")
            return MIN_TRADE_AMOUNT

    # 추가: 심볼 목록 검증 메서드
    def verify_symbols(self, symbols):
        try:
            markets = self.fetch_markets_sync()
            if markets is None:
                return []
            valid_symbols = [symbol for symbol in symbols if symbol in markets]
            removed_symbols = set(symbols) - set(valid_symbols)
            if removed_symbols:
                error_logger.warning(f"다음 심볼이 제거되었거나 존재하지 않습니다: {removed_symbols}")
            return valid_symbols
        except Exception as e:
            error_logger.error(f"심볼 목록 검증 오류: {e}")
            traceback.print_exc()
            return symbols  # 검증에 실패하면 기존 심볼 목록을 반환

# ============================
# AI Decision Maker
# ============================

class AIDecisionMaker:
    def __init__(self, model_path=MODEL_PATH, scaler_path=SCALER_PATH, label_encoder_path=LABEL_ENCODER_PATH):
        self.model_path = model_path
        self.scaler_path = scaler_path
        self.label_encoder_path = label_encoder_path
        self.model = None
        self.scaler = None
        self.label_encoder = None
        self.performance_threshold = 0.7  # 성능 기준 (예: 70% 정확도 이하이면 재학습)
        self.performance_last_checked = time.time()  # 마지막 성능 체크 시간
        self.load_model()

    def load_model(self):
        """
        모델 로드 또는 훈련.
        """
        if not os.path.exists(self.model_path):
            general_logger.info("AI 모델 파일이 존재하지 않습니다. 모델을 훈련시킵니다.")
            self.train_model()
        else:
            try:
                self.model = joblib.load(self.model_path)
                general_logger.info("AI 모델 로드 성공")
                if os.path.exists(self.scaler_path):
                    self.scaler = joblib.load(self.scaler_path)
                    general_logger.info("Scaler 로드 성공")
                else:
                    self.scaler = StandardScaler()
                    general_logger.warning("Scaler 파일이 없어서 새로 초기화됨")

                if os.path.exists(self.label_encoder_path):
                    self.label_encoder = joblib.load(self.label_encoder_path)
                    general_logger.info("Label Encoder 로드 성공")
                else:
                    self.label_encoder = LabelEncoder()
                    general_logger.warning("Label Encoder 파일이 없어서 새로 초기화됨")
            except Exception as e:
                error_logger.error(f"AI 모델 로드 실패: {e}")
                self.model = None

    def prepare_dataset(self, df, symbol):
        """
        데이터셋 준비: 기술 지표 계산 및 데이터 정리.
        :param df: pandas DataFrame containing OHLCV data
        :param symbol: 거래 심볼
        :return: features (X), target (y)
        """
        try:
            # 기술 지표 계산
            df['EMA_short'] = df['close'].ewm(span=EMA_SHORT_PERIOD).mean()
            df['EMA_long'] = df['close'].ewm(span=EMA_LONG_PERIOD).mean()
            df['MACD'] = df['close'].ewm(span=MACD_SHORT_PERIOD).mean() - df['close'].ewm(span=MACD_LONG_PERIOD).mean()
            df['MACD_signal'] = df['MACD'].ewm(span=MACD_SIGNAL_PERIOD).mean()
            df['RSI'] = 100 - (100 / (1 + df['close'].pct_change().rolling(RSI_PERIOD).mean() / abs(df['close'].pct_change().rolling(RSI_PERIOD).mean())))

            # 결측값 제거
            df = df.dropna()

            # 특성과 타겟 정의
            X = df[['EMA_short', 'EMA_long', 'MACD', 'MACD_signal', 'RSI']]
            y = (df['close'].shift(-1) > df['close']).astype(int)  # 다음 캔들의 가격이 상승하면 1, 하락하면 0

            general_logger.info(f"{symbol} 데이터셋 준비 완료: {len(X)}개의 샘플")
            return X, y
        except Exception as e:
            error_logger.error(f"{symbol} 데이터셋 준비 중 오류: {e}")
            return None, None

    def predict(self, indicators):
        """
        AI 모델을 사용하여 거래 신호 예측.
        """
        if not self.model or not self.scaler or not self.label_encoder:
            error_logger.error("AI 모델, Scaler, 또는 Label Encoder가 로드되지 않았습니다.")
            return 'HOLD'

        try:
            feature_vector = [
                indicators.get('EMA_short', 0),
                indicators.get('EMA_long', 0),
                indicators.get('MACD', 0),
                indicators.get('MACD_signal', 0),
                indicators.get('RSI', 50)
            ]
            X = np.array(feature_vector).reshape(1, -1)
            if self.scaler:
                X = self.scaler.transform(X)

            prediction_encoded = self.model.predict(X)[0]
            prediction = self.label_encoder.inverse_transform([prediction_encoded])[0]
            return prediction
        except Exception as e:
            error_logger.error(f"AI 예측 오류: {e}")
            return 'HOLD'

    def retrain_model(self):
        """
        Retrain the AI model with the latest data.
        """
        general_logger.info("AI 모델 재훈련을 시작합니다.")
        self.train_model()
        general_logger.info("AI 모델 재훈련이 완료되었습니다.")

# ============================
# Trading System
# ============================

class TradingSystem:
    def __init__(self):
        self.binance_api = BinanceAPI(BINANCE_API_KEY, BINANCE_API_SECRET)
        self.decision_maker = AIDecisionMaker()
        self.position = {}  # Dictionary to hold current positions
        self.trade_history = self.load_trade_history()  # 거래 기록 로드
        self.markets = self.binance_api.fetch_markets_sync()
        if self.markets is None:
            raise Exception("시장을 로드할 수 없습니다.")
        self.symbols = self.get_trading_symbols()
        self.performance_last_checked = time.time()  # 성능 체크 시간 초기화
        general_logger.info(f"Trading symbols loaded: {self.symbols}")

    def load_trade_history(self):
        """
        거래 기록을 로드하는 메서드.
        """
        try:
            if os.path.exists(TRADE_HISTORY_FILE):
                trade_history_df = pd.read_csv(TRADE_HISTORY_FILE)
                general_logger.info(f"거래 기록 로드됨: {len(trade_history_df)}개의 거래 기록.")
                return trade_history_df
            else:
                general_logger.warning(f"거래 기록 파일이 존재하지 않습니다. 새로 시작합니다.")
                return pd.DataFrame()  # 빈 데이터프레임 반환
        except Exception as e:
            error_logger.error(f"거래 기록 로드 오류: {e}")
            traceback.print_exc()
            return pd.DataFrame()  # 오류 발생 시 빈 데이터프레임 반환

    def apply_coin_filter(self, symbols):
        """
        필터링 조건을 적용하여 심볼 목록을 반환하는 함수입니다.
        예시로 거래량 기준으로 필터링하고, 시장 캡 등 추가적인 필터링을 할 수 있습니다.
        """
        try:
            ticker_data = self.binance_api.binance.fetch_tickers()
            symbols_with_volume = []
            for symbol in symbols:
                ticker = ticker_data.get(symbol, {})
                volume = ticker.get('quoteVolume', 0)
                if volume >= COIN_FILTER_CONFIG['min_volume']:
                    symbols_with_volume.append(symbol)

            # 거래량 상위 N개 심볼 선택
            sorted_symbols = sorted(symbols_with_volume, key=lambda s: ticker_data[s]['quoteVolume'], reverse=True)
            top_n_symbols = sorted_symbols[:COIN_FILTER_CONFIG['top_n']]  

            # 예시로 가격 변동성 기준 필터링
            final_symbols = []
            for symbol in top_n_symbols:
                ticker = ticker_data.get(symbol, {})
                price_change = ticker.get('percentage', 0)  # 가격 변동률
                if abs(price_change) >= COIN_FILTER_CONFIG['min_price_volatility']:
                    final_symbols.append(symbol)

            general_logger.info(f"필터링 후 심볼 수: {len(final_symbols)}")
            return final_symbols

        except Exception as e:
            error_logger.error(f"심볼 필터링 오류: {e}")
            traceback.print_exc()
            return symbols  # 필터링 실패 시 모든 심볼 반환

    def get_trading_symbols(self):
        """
        거래 가능한 심볼을 필터링하여 반환합니다.
        """
        symbols = [symbol for symbol in self.markets if '/USDT' in symbol]
        # 심볼 검증
        symbols = self.binance_api.verify_symbols(symbols)
        # 필터링 조건 적용
        filtered_symbols = self.apply_coin_filter(symbols)
        return filtered_symbols

    def run(self):
        """
        트레이딩 로직을 실행하고 성능을 주기적으로 체크하는 함수.
        """
        while True:
            try:
                for symbol in self.symbols:
                    self.trade_logic(symbol)

                    # 트레이딩 후 주기적으로 성능 체크 및 재학습 유도
                    if time.time() - self.performance_last_checked > 86400:  # 하루에 한 번 성능 체크
                        # X_test, y_test는 현재 모델에서 예측할 수 있는 데이터셋
                        self.decision_maker.check_and_retrain(X_test, y_test)

                    time.sleep(TRADE_INTERVAL)
            except Exception as e:
                error_logger.error(f"메인 루프 오류: {e}")
                traceback.print_exc()
                time.sleep(TRADE_INTERVAL)

    def trade_logic(self, symbol):
        """
        트레이딩 로직을 실행하는 함수.
        """
        general_logger.info(f"거래 로직 실행 중: {symbol}")
        df = self.binance_api.fetch_historical_ohlcv_sync(symbol, timeframe='1h', limit=100)
        if df is None or df.empty:
            error_logger.error(f"{symbol}의 데이터가 없습니다.")
            return

        # Calculate indicators for the latest data point
        X, y = self.decision_maker.prepare_dataset(df, symbol)  # symbol을 전달하도록 수정
        if X is None or y is None:
            error_logger.error(f"{symbol}의 데이터셋 준비 실패.")
            return

        if X.empty:
            error_logger.error(f"{symbol}의 데이터셋이 비어 있습니다.")
            return

        latest_indicators = X.iloc[-1].to_dict()
        signal = self.decision_maker.predict(latest_indicators)
        general_logger.info(f"{symbol}의 신호: {signal}")

        current_position = self.position.get(symbol, {'side': None, 'amount': 0})

        if signal == 'BUY' and current_position['side'] != 'LONG':
            self.execute_order(symbol, 'buy')
        elif signal == 'SELL' and current_position['side'] != 'SHORT':
            self.execute_order(symbol, 'sell')
        elif signal == 'AVERAGE_DOWN' and current_position['side'] == 'LONG':
            self.execute_order(symbol, 'buy', average=True)
        # Add more conditions as needed

    def execute_order(self, symbol, side, average=False):
        general_logger.info(f"{symbol}에 대한 주문 실행: {side}, 평균 매수: {average}")
        balance = self.binance_api.fetch_balance_sync()
        if balance is None:
            error_logger.error("잔고 정보를 가져올 수 없습니다.")
            return

        usdt_balance = balance['total'].get('USDT', 0) * (1 - RESERVE_RATIO)
        if usdt_balance < MIN_TRADE_AMOUNT:
            error_logger.warning("USDT 잔고가 최소 거래 금액보다 적습니다.")
            return

        # Determine order amount based on available balance and exposure
        last_price = self.get_last_price(symbol)
        if last_price == 0:
            error_logger.error(f"{symbol}의 마지막 가격이 유효하지 않습니다.")
            return

        amount = (usdt_balance * MAX_PORTFOLIO_EXPOSURE) / last_price
        min_amount = self.binance_api.fetch_minimum_trade_amount_sync(symbol)
        amount = max(amount, MIN_TRADE_AMOUNT / last_price)

        # Place order
        order = self.binance_api.place_order_sync(symbol, side.upper(), amount)
        if order:
            # Update position
            self.position[symbol] = {'side': side.upper(), 'amount': amount}
            # Log trade history
            trade = {
                'timestamp': datetime.utcnow(),
                'symbol': symbol,
                'action': side.upper(),
                'price': order.get('average', last_price),
                'amount': amount,
                'order_id': order.get('id', 'N/A')
            }
            self.trade_history = self.trade_history.append(trade, ignore_index=True)
            self.save_trade_history()
            general_logger.info(f"{symbol}에 대한 {side.upper()} 주문이 성공적으로 실행되었습니다.")
        else:
            error_logger.error(f"{symbol}에 대한 {side.upper()} 주문이 실패했습니다.")

    def get_last_price(self, symbol):
        ticker = self.binance_api.fetch_ticker_sync(symbol)
        if ticker and 'last' in ticker:
            return ticker['last']
        else:
            error_logger.error(f"{symbol}의 마지막 가격을 가져올 수 없습니다.")
            return 0

# ============================
# Main Execution
# ============================

if __name__ == "__main__":
    try:
        bot = TradingSystem()
        bot.run()
    except Exception as e:
        error_logger.critical(f"트레이딩 시스템 시작 중 치명적인 오류 발생: {e}")
        traceback.print_exc()
