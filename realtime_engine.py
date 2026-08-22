import ccxt.async_support as ccxt  # Dùng async để giảm lag
import pandas as pd
import numpy as np
import asyncio

# --- CẤU HÌNH CHUNG ---
symbol = 'TAO/USDT'
timeframe = '1h'
days_history = 50

INDICATORS = {
    'rsi_length': 14,
    'macd_fast': 12,
    'macd_slow': 26,
    'macd_signal': 9,
    'ema_short': 9,
    'ema_long': 50,
    'bb_period': 20,
    'bb_std': 2.0
}

class BinanceAnalysisEngine:
    def __init__(self, symbol=symbol, timeframe=timeframe):
        self.exchange = ccxt.binance({'enableRateLimit': True})
        self.symbol = symbol
        self.timeframe = timeframe
        self.indicators = INDICATORS

    async def fetch_real_data(self):
        """LẤY DỮ LIỆU THẬT TỪ BINANCE"""
        try:
            print(f"Đang kết nối Binance API... Lấy dữ liệu cho {self.symbol} trên khung {self.timeframe}")

            ohlcv = await self.exchange.fetch_ohlcv(
                self.symbol,
                self.timeframe,
                limit=days_history * 24
            )

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['time'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            latest_price = df.iloc[-1]['close']
            print(f"✅ Giá {self.symbol} hiện tại: ${latest_price:.2f}")
            return df

        except Exception as e:
            print(f"❌ Lỗi kết nối Binance API: {e}")
            return None
        finally:
            # Bắt buộc đóng kết nối async sau khi lấy xong dữ liệu
            await self.exchange.close()

    def calculate_indicators(self, df):
        """Tính toán tất cả chỉ báo"""
        if df is None:
            return {}

        last_row = df.iloc[-1]
        current_price = last_row['close']

        # --- 1. TÍNH RSI (Sửa lỗi cú pháp ngoặc đơn) ---
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.indicators['rsi_length']).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.indicators['rsi_length']).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi = rsi.fillna(50)

        # --- 2. TÍNH MACD ---
        fast_ema = df['close'].ewm(span=self.indicators['macd_fast'], adjust=False).mean()
        slow_ema = df['close'].ewm(span=self.indicators['macd_slow'], adjust=False).mean()
        macd_line = fast_ema - slow_ema
        signal_ema = macd_line.ewm(span=self.indicators['macd_signal'], adjust=False).mean()

        # --- 3. TÍNH EMA ---
        ema_short = df['close'].ewm(span=self.indicators['ema_short'], adjust=False).mean()
        ema_long = df['close'].ewm(span=self.indicators['ema_long'], adjust=False).mean()

        # --- 4. TÍNH BOLLINGER BANDS ---
        bb_middle = df['close'].rolling(window=self.indicators['bb_period']).mean()
        bb_std = df['close'].rolling(window=self.indicators['bb_period']).std() * self.indicators['bb_std']
        bb_upper = bb_middle + bb_std
        bb_lower = bb_middle - bb_std

        return {
            'price': current_price,
            'rsi': rsi.iloc[-1],
            'macd_line': macd_line.iloc[-1],
            'macd_signal': signal_ema.iloc[-1] if not np.isnan(signal_ema.iloc[-1]) else 0,
            'ema_short': ema_short.iloc[-1],
            'ema_long': ema_long.iloc[-1],
            'bb_upper': bb_upper.iloc[-1],
            'bb_lower': bb_lower.iloc[-1],
            'df': df
        }

    def analyze_market_logic(self, indicators):
        """LOGIC PHÂN TÍCH THỊ TRƯỜNG"""
        if not indicators:
            return {'signal': 'ERROR', 'confidence': 0, 'reasoning': 'Không có dữ liệu.'}

        price = indicators['price']
        rsi = indicators['rsi']
        macd_line = indicators['macd_line']
        macd_signal = indicators['macd_signal']
        ema_short = indicators['ema_short']
        ema_long = indicators['ema_long']
        bb_lower = indicators['bb_lower']
        bb_upper = indicators['bb_upper']

        signal_result = {'signal': 'HOLD', 'confidence': 0, 'reasoning': ''}

        # Sửa lại điều kiện RSI chuẩn kỹ thuật (30 quá bán, 70 quá mua)
        if ema_short > ema_long and rsi < 65 and macd_line > macd_signal:
            signal_result['signal'] = 'BUY STRONG 🚀'
            signal_result['confidence'] = 85
            signal_result['reasoning'] += f"✅ Xu hướng lên (EMA9 > EMA50). RSI ở mức {rsi:.2f}. MACD cắt lên.\n"

        elif price < bb_lower and rsi < 35:
            signal_result['signal'] = 'BUY MODERATE 🔽'
            signal_result['confidence'] = 65
            signal_result['reasoning'] += f"⚠️ Giá chạm dải dưới BB (${bb_lower:.2f}), RSI quá bán ({rsi:.2f}). Khả năng bật tăng cao.\n"

        elif ema_short < ema_long and rsi > 65:
            signal_result['signal'] = 'SELL STRONG 📉'
            signal_result['confidence'] = 80
            signal_result['reasoning'] += f"⛔ Xu hướng giảm (EMA9 < EMA50). RSI quá mua ({rsi:.2f}).\n"

        elif bb_lower <= price <= bb_upper:
            signal_result['signal'] = 'HOLD'
            signal_result['confidence'] = 20
            signal_result['reasoning'] += f"⏳ Giá đang đi Sideways trong dải BB (${bb_lower:.2f} - ${bb_upper:.2f}).\n"

        return signal_result

    async def run_analysis(self):
        """Chạy toàn bộ quy trình bất đồng bộ"""
        try:
            df = await self.fetch_real_data()

            if df is None:
                print("Không thể lấy dữ liệu. Vui lòng kiểm tra kết nối internet.")
                return

            indicators = self.calculate_indicators(df)
            result = self.analyze_market_logic(indicators)

            print("\n" + "="*60)
            print(f"TÍN HIỆU PHÂN TÍCH CHO {self.symbol}")
            print("="*60)
            print(f"📈 Giá hiện tại: ${indicators['price']:.2f}")
            print(f"📊 RSI: {indicators['rsi']:.2f}")
            print(f"🔺 MACD: {indicators['macd_line']:.4f} | Signal: {indicators['macd_signal']:.4f}")
            print(f"📏 EMA Ngắn ({self.indicators['ema_short']}): ${indicators['ema_short']:.2f}")
            print(f"📏 EMA Dài ({self.indicators['ema_long']}): ${indicators['ema_long']:.2f}")
            print(f"⚪ Bollinger Upper: ${indicators['bb_upper']:.2f} | Lower: ${indicators['bb_lower']:.2f}")
            print("="*60)
            print(f"🎯 TÍN HIỆU CHỐT: {result['signal']}")
            print(f"💪 Độ tin cậy: {result['confidence']}%")
            print(f"📝 Lý do: {result['reasoning']}")
            print("="*60 + "\n")

        except Exception as e:
            print(f"Lỗi khi phân tích: {e}")

if __name__ == "__main__":
    engine = BinanceAnalysisEngine()
    asyncio.run(engine.run_analysis())