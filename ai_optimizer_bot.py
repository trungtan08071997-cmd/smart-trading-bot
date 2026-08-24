import pandas as pd
import pandas_ta as ta
import ccxt
import json
from datetime import datetime, timedelta
import os
import time
import csv
import random

class SmartOptimizedBot:
    def __init__(self, symbol="BTC/USDT"):
        self.symbol = symbol
        self.exchange = ccxt.coinbase()
        self.config_file = "config.json"
        self.log_file = "trade_history.csv"
        self.last_optimization_time = 0
        self.load_config()
        self.last_action_update = 0   # NEW: theo dõi lần cập nhật action.csv

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
            'Timestamp', 'Price', 'RSI', 'MACD', 'Volume',
            'BB_Width', 'Score_Total', 'Confidence', 'Signal_Action', 'News', 'Sentiment', 'SL', 'TP', 'News_Date'
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
                    signal_data['sentiment'],   # thêm sentiment vào đây
                    signal_data['sl'],
                    signal_data['tp'],
                    signal_data['news_date']   # lưu ngày tin tức xuất bản
                ])
            print(f"[LOG] Đã ghi tín hiệu vào file: {self.log_file}")
        except Exception as e:
            print(f"Lỗi khi lưu log: {e}")

    def update_action_csv(self, signal):
        headers = ['Timestamp', 'Price', 'Action', 'Confidence']
        with open("action.csv", 'w', newline='') as f:   # luôn ghi đè
            writer = csv.writer(f)
            writer.writerow(headers)
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                signal['price'],
                signal['action'],
                signal['confidence']
            ])
        print("[ACTION] Đã cập nhật action.csv")

    def fetch_and_analyze(self):
        try:
            # 1. Fetch dữ liệu OHLCV
            bars = self.exchange.fetch_ohlcv(self.symbol, '1h', limit=1000)
            if not bars or len(bars) < 30:
                print(f"[INFO] Chưa đủ dữ liệu lịch sử ({len(bars)} nến), chờ thêm...")
                return None

            df = pd.DataFrame(bars, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df.set_index('time', inplace=True)

            # 2. Kiểm tra đủ dữ liệu để tính chỉ báo
            min_required = max(
                30,
                self.config['params']['MACD_Fast'] + self.config['params']['MACD_Slow'],
                self.config['params']['RSI_Period']
            )
            if len(df) < min_required:
                print(f"[INFO] Dữ liệu chưa đủ để tính chỉ báo (cần {min_required}). Đợi lần sau...")
                return None

            last_row = df.iloc[-1]

            # --- B. RSI ---
            df['rsi'] = ta.rsi(df['close'], length=self.config['params']['RSI_Period'])
            rsi = df['rsi'].iloc[-1] if not pd.isna(df['rsi'].iloc[-1]) else 50.0

            # --- C. MACD ---
            macd_full = ta.macd(
                df['close'],
                fast=self.config['params']['MACD_Fast'],
                slow=self.config['params']['MACD_Slow'],
                signal=9
            )
            df['macd'] = macd_full.iloc[:, 0]   # MACD line
            df['macd_signal'] = macd_full.iloc[:, 1]   # Signal line
            macd_val = df['macd'].iloc[-1]
            macd_signal = df['macd_signal'].iloc[-1]

            # --- D. Bollinger Bands ---
            bb_full = ta.bbands(df['close'], length=self.config['params']['Bollinger_Period'], std=2.0)
            df['bb_upper'] = bb_full.iloc[:, 0]
            df['bb_lower'] = bb_full.iloc[:, 2]
            df['bb_width'] = df['bb_upper'] - df['bb_lower']

            bb_upper = df['bb_upper'].iloc[-1]
            bb_lower = df['bb_lower'].iloc[-1]
            bb_width = df['bb_width'].iloc[-1]

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
            print(f"[LỖI SYSTEM] Lỗi xử lý chung: {e}")
            import traceback
            traceback.print_exc()
            return None


    def fetch_news(self):
        try:
            # Gọi search_web để lấy tin tức mới nhất về Bitcoin
            # (ở đây giả lập, thực tế bạn cần parse từ kết quả search_web)
            news_data = {
                "news": "Bitcoin jumps 8.7% to $69,749 after US Treasury bond buyback plan",
                "sentiment_boost": 1,
                "date": "2026-08-20 09:51:00"   # ngày xuất bản từ web
            }
            return news_data

        except Exception as e:
            print(f"[NEWS ERROR] {e}")
            # fallback nếu lỗi
            return {
                "news": "No fresh news available",
                "sentiment_boost": 0,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def sentiment_score(self, sentiment_boost):
        # Trả về điểm số sentiment dựa trên boost đã tính sẵn
        return sentiment_boost * self.config['params']['News_Weight']

    def analyze_signal(self, ind):
        if ind is None: return None

        score = 0.0

        # RSI Logic (Cân bằng hơn)
        if ind['rsi'] < 30:
            score += 3.0
        elif ind['rsi'] > 70:
            score -= 3.0

        # MACD Logic
        if ind['macd'] > ind['macd_signal']:
            score += 2.5
        elif ind['macd'] < -ind['macd_signal']: # Divergence potential
             score -= 1.0

        # Bollinger Bands Logic (Sửa logic cũ)
        # Nếu giá gần Upper Band, coi là overbought (giảm điểm), nếu gần Lower Band tăng điểm
        if ind['bb_width'] > 0:
            percent_price = (ind['price'] - ind['bb_lower']) / ind['bb_width']
            if percent_price > 0.8: # Gần Upper Band
                score -= 2.0
            elif percent_price < 0.2: # Gần Lower Band
                score += 2.0
        else:
            # Trường hợp BB chập chờn
            if ind['price'] < 10000: # Placeholder check, nếu price thấp hơn threshold nào đó
                 score += 1.0

        # Volume Logic (Tối ưu)
        # So sánh volume hiện tại với trung bình 20 phiên trước
        # df_vol = pd.DataFrame(ind.get('volume', 0)) 
        # Lưu ý: Để lấy được volume history cần fetch thêm dataframe, ở đây giả định logic đơn giản
        if ind['volume'] > 1000: # Ví dụ check absolute value cho demo
            score += 0.5

        # Sentiment Logic
        news_data = self.fetch_news()
        sentiment_points = self.sentiment_score(news_data['sentiment_boost'])
        score += sentiment_points

        current_threshold = float(self.config['params']['Signal_Threshold'])
        
        # Xác định hành động
        if score > current_threshold:
            action = "BUY"
        elif score < -current_threshold:
            action = "SELL"
        else:
            action = "HOLD"

        # Confidence Score
        confidence = min(abs(score) * 10, 100)

        # Thêm SL và TP
        if action == "BUY":
            sl = ind['price'] * 0.98
            tp = ind['price'] * 1.04
        elif action == "SELL":
            sl = ind['price'] * 1.02
            tp = ind['price'] * 0.96
        else:
            sl = None
            tp = None

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
        print("SMART TRADING ADVISOR V3 - Optimized Edition")
        print("=" * 40)

        # Bắt đầu check config ban đầu
        self.check_retraining() 

        while True:
            try:
                ind = self.fetch_and_analyze()
                if ind is not None:
                    signal = self.analyze_signal(ind)
                    if signal:
                        print(f"\n--- [GHI CHÉP] {datetime.now().strftime('%H:%M')} ---")
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

            time.sleep(300) # Chờ 5 phút cho mỗi chu kỳ

        # Phần này sẽ không bao giờ chạy vì while True, nhưng nếu break ra được thì chạy
        if os.path.exists(self.log_file):
             self.save_config()

if __name__ == "__main__":
    try:
        bot = SmartOptimizedBot(symbol="BTC/USDT")
        bot.run()
    except KeyboardInterrupt:
        print("\n\n=== ĐÃ DỪNG BOT ===")
