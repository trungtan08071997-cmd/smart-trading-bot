import pandas as pd
import pandas_ta as ta
import json
from datetime import datetime, timedelta
import os
import time
import csv
from binance import ThreadedWebsocketManager

class SmartOptimizedBot:
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.df = pd.DataFrame()
        self.twm = ThreadedWebsocketManager()
        self.twm.start()
        self.config_file = "config.json"
        self.log_file = "trade_history.csv"
        self.last_optimization_time = 0
        self.load_config()
        self.last_action_update = 0

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        else:
            self.config = {
                "symbol": self.symbol,
                "timeframe": "1h",
                "params": {
                    "RSI_Period": 6,
                    "MACD_Fast": 12,
                    "MACD_Slow": 26,
                    "EMA_Periods": [9, 20],
                    "Bollinger_Period": 20,
                    "ATR_Length": 14,
                    "Signal_Threshold": 5.0,
                    "News_Weight": 0.5
                },
                "optimization": {
                    "save_logs_to_csv": self.log_file,
                    "recovery_days": 7,
                    "auto_adjust_mode": True
                }
            }

    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=4)

    def log_signal_to_csv(self, signal_data):
        file_exists = os.path.exists(self.log_file) and os.path.getsize(self.log_file) > 0
        mode = 'a' if file_exists else 'w'
        headers = [
            'Date', 'Time', 'Price', 'RSI', 'MACD', 'Volume',
            'BB_Width', 'Score_Total', 'Confidence', 'Signal_Action',
            'News', 'Sentiment', 'SL', 'TP', 'News_Date'
        ]
        try:
            with open(self.log_file, mode, newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(headers)
                writer.writerow([
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    signal_data['price'],
                    round(signal_data['rsi'], 2),
                    round(signal_data['macd'], 4),
                    round(signal_data['volume'], 2),
                    round(signal_data['bb_width'], 4),
                    round(signal_data['score'], 2),
                    f"{signal_data['confidence']:.1f}%",
                    signal_data['action'],
                    signal_data['news'],
                    signal_data['sentiment'],
                    signal_data['sl'],
                    signal_data['tp'],
                    signal_data['news_date']
                ])
            print(f"[LOG] Đã ghi tín hiệu vào file: {self.log_file}")
        except Exception as e:
            print(f"Lỗi khi lưu log: {e}")

    def update_action_csv(self, signal):
        headers = ['Date', 'Time', 'Price', 'Action', 'Confidence']
        with open("action.csv", 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                signal['price'],
                signal['action'],
                signal['confidence']
            ])
        print("[ACTION] Đã cập nhật action.csv")

    def handle_kline(self, msg):
        kline = msg['k']
        t = pd.to_datetime(kline['t'], unit='ms')
        close = float(kline['c'])
        volume = float(kline['v'])

        new_row = {"time": t, "close": close, "volume": volume}
        self.df = pd.concat([self.df, pd.DataFrame([new_row])]).drop_duplicates(subset="time", keep="last")
        self.df.set_index("time", inplace=True)

        print(f"[WS] {self.symbol} Close={close}, Vol={volume}")

        ind = self.fetch_and_analyze()
        if ind:
            signal = self.analyze_signal(ind)
            if signal:
                self.log_signal_to_csv(signal)
                if time.time() - self.last_action_update > 3600:
                    self.update_action_csv(signal)
                    self.last_action_update = time.time()

    def fetch_and_analyze(self):
        try:
            if len(self.df) < 30:
                print("[INFO] Chưa đủ dữ liệu từ WebSocket, chờ thêm...")
                return None

            last_row = self.df.iloc[-1]

            self.df['rsi'] = ta.rsi(self.df['close'], length=self.config['params']['RSI_Period'])
            rsi = self.df['rsi'].iloc[-1] if not pd.isna(self.df['rsi'].iloc[-1]) else 50.0

            macd_full = ta.macd(
                self.df['close'],
                fast=self.config['params']['MACD_Fast'],
                slow=self.config['params']['MACD_Slow'],
                signal=9
            )
            self.df['macd'] = macd_full.iloc[:, 0]
            self.df['macd_signal'] = macd_full.iloc[:, 1]
            macd_val = self.df['macd'].iloc[-1]
            macd_signal = self.df['macd_signal'].iloc[-1]

            bb_full = ta.bbands(self.df['close'], length=self.config['params']['Bollinger_Period'], std=2.0)
            self.df['bb_upper'] = bb_full.iloc[:, 0]
            self.df['bb_lower'] = bb_full.iloc[:, 2]
            self.df['bb_width'] = self.df['bb_upper'] - self.df['bb_lower']

            bb_upper = self.df['bb_upper'].iloc[-1]
            bb_lower = self.df['bb_lower'].iloc[-1]
            bb_width = self.df['bb_width'].iloc[-1]

            price = last_row['close']
            volume = last_row['volume']

            return {
                "price": float(price),
                "rsi": float(rsi),
                "macd": float(macd_val),
                "macd_signal": float(macd_signal),
                "bb_upper": float(bb_upper),
                "bb_lower": float(bb_lower),
                "bb_width": float(bb_width),
                "volume": float(volume)
            }

        except Exception as e:
            print(f"[LỖI SYSTEM] Lỗi xử lý WebSocket: {e}")
            return None

    def fetch_news(self):
        try:
            return {
                "news": "Bitcoin jumps 8.7% to $69,749 after US Treasury bond buyback plan",
                "sentiment_boost": 1,
                "date": "2026-08-20 09:51:00"
            }
        except Exception as e:
            print(f"[NEWS ERROR] {e}")
            return {
                "news": "No fresh news available",
                "sentiment_boost": 0,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def sentiment_score(self, sentiment_boost):
        return sentiment_boost * self.config['params']['News_Weight']

    def analyze_signal(self, ind):
        if ind is None: return None
        score = 0.0

        if ind['rsi'] < 30: score += 3.0
        elif ind['rsi'] > 70: score -= 3.0

        if ind['macd'] > ind['macd_signal']: score += 2.5
        elif ind['macd'] < -ind['macd_signal']: score -= 1.0

        if ind['bb_width'] > 0:
            percent_price = (ind['price'] - ind['bb_lower']) / ind['bb_width']
            if percent_price > 0.8: score -= 2.0
            elif percent_price < 0.2: score += 2.0

        if ind['volume'] > 1000: score += 0.5

        news_data = self.fetch_news()
        sentiment_points = self.sentiment_score(news_data['sentiment_boost'])
        score += sentiment_points

        threshold = float(self.config['params']['Signal_Threshold'])
        if score > threshold: action = "BUY"
        elif score < -threshold: action = "SELL"
        else: action = "HOLD"

        confidence = min(abs(score) * 10, 100)

        if action == "BUY":
            sl = ind['price'] * 0.98
            tp = ind['price'] * 1.04
        elif action == "SELL":
            sl = ind['price'] * 1.02
            tp = ind['price'] * 0.96
        else:
            sl = None; tp = None

        return {
            "price": ind['price'],
            "rsi": round(ind['rsi'], 2),
            "macd": round(ind['macd'], 4),
            "bb_width": round(ind['bb_width'], 4),
            "volume": round(ind['volume'], 2),
            "score": round(score, 2),
            "confidence": round(confidence, 1),
            "action": action,
            "news": news_data["news"],
            "sentiment": round(sentiment_points, 2),
            "sl": sl,
            "tp": tp,
            "news_date": news_data["date"]   # thêm ngày tin tức          
        }

    def check_retraining(self):
        # Chỉ kiểm tra mỗi 24 giờ hoặc khi khởi động để tránh load file liên tục
        now = time.time()
        if now - self.last_optimization_time < 86400: # 86400 seconds = 1 day
            return

        try:
            if not os.path.exists(self.log_file) or os.path.getsize(self.log_file) == 0:
                print("📊 File log chưa có dữ liệu. Skip auto-optimization.")
                self.last_optimization_time = now
                return

            df_log = pd.read_csv(self.log_file)
            start_date = datetime.now() - timedelta(days=3)
            
            # Lọc chỉ các lệnh KHÔNG phải HOLD để đánh giá hiệu suất
            active_signals = df_log[df_log['Signal_Action'] != 'HOLD']

            if len(active_signals) > 10:
                # Giả định Score_Total > 5 là thắng (đây là logic demo)
                winning_signals = active_signals[active_signals['Score_Total'] > 5]
                success_rate = (len(winning_signals) / len(active_signals)) * 100
                
                print(f"\n=== KIỂM TRA HIỆU SUẤT ===")
                print(f"Tín hiệu Active: {len(active_signals)}")
                print(f"Success Rate: {success_rate:.2f}%")

                if success_rate < 60 and self.config['params']['Signal_Threshold'] < 15:
                    print("⚠️ HIỆU SUẤT THẤP: Tự động điều chỉnh độ nhạy")
                    current_val = self.config['params']['Signal_Threshold']
                    self.config['params']['Signal_Threshold'] += 1.0 # Tăng ngưỡng để ít tín hiệu ảo hơn
                    self.save_config()
                    print(f"Cập nhật Signal_Threshold: {current_val} -> {self.config['params']['Signal_Threshold']}")
                
                elif success_rate > 75:
                    print("✅ Hiệu suất xuất sắc: Không cần điều chỉnh.")
            
            else:
                print(f"📊 Dữ liệu chưa đủ (Active signals < 10). Skip auto-optimization.")

            # === NEW LOGIC ===
            # Kiểm tra HOLD liên tục 4 ngày
            hold_signals = df_log[df_log['Signal_Action'] == 'HOLD']
            if not hold_signals.empty:
                last_hold_date = pd.to_datetime(hold_signals['Timestamp']).max()
                if (datetime.now() - last_hold_date).days >= 4:
                    print("⚠️ HOLD liên tục 4 ngày → cập nhật tham số")
                    self.config['params']['Signal_Threshold'] = max(3.0, self.config['params']['Signal_Threshold'] - 1.0)
                    self.save_config()

            # Kiểm tra lệnh sai >30%
            loss_signals = active_signals[active_signals['Score_Total'] < -30]
            if not loss_signals.empty:
                print("⚠️ Lệnh sai trên 30% → cập nhật tham số")
                self.config['params']['RSI_Period'] = min(14, self.config['params']['RSI_Period'] + 2)
                self.save_config()


        except Exception as e:
            print(f"Lỗi khi tối ưu hóa tự động: {e}")
        
        self.last_optimization_time = now

    def run(self):
    print("=" * 40)
    print("SMART TRADING ADVISOR V3 - WebSocket Edition")
    print("=" * 40)

    # Bắt đầu stream nến 1h
    self.twm.start_kline_socket(callback=self.handle_kline, symbol=self.symbol, interval="1h")
    self.twm.join()

        while True:
            try:
                ind = self.fetch_and_analyze()
                if ind is not None:
                    signal = self.analyze_signal(ind)
                    if signal:
                        print(f"\n--- [GHI CHÉP] {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} ---")
                        print(f"Giá BTC: ${signal['price']:.2f} | RSI: {signal['rsi']} | MACD: {signal['macd']} | BB_Width: {signal['bb_width']} | Vol: {signal['volume']}")
                        print(f"Tín hiệu AI: {signal['action']} | Score: {signal['score']:.1f} | Conf: {signal['confidence']:.0f}%")
                        print(f"News: {signal['news']} (Sentiment: {signal['sentiment']}, Date: {signal['news_date']})")

                        # Lưu log nếu có hành động mua/bán để giảm noise trong file
                        #if signal['action'] != 'HOLD':
                        self.log_signal_to_csv(signal)

                        # 👉 NEW: gọi update_action_csv mỗi 1 tiếng
                        if time.time() - self.last_action_update > 3600:
                            self.update_action_csv(signal)
                            self.last_action_update = time.time()

                else:
                    print("[WAIT] Chờ dữ liệu...")

                # Kiểm tra tối ưu hóa định kỳ (bên trong hàm đã kiểm tra thời gian rồi)
                self.check_retraining()

            except Exception as e:
                print(f"[ERROR] Lỗi hệ thống: {e}")

            time.sleep(1800) # Chờ 30 phút cho mỗi chu kỳ

        # Phần này sẽ không bao giờ chạy vì while True, nhưng nếu break ra được thì chạy
        if os.path.exists(self.log_file):
             self.save_config()

if __name__ == "__main__":
    try:
        bot = SmartOptimizedBot(symbol="BTC/USDT")
        bot.run()
    except KeyboardInterrupt:
        print("\n\n=== ĐÃ DỪNG BOT ===")
