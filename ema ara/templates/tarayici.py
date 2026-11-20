import os
import time
import threading
import ccxt
import pandas as pd
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

tarama_durumu = {
    "aktif": False,
    "zaman_dilimi": "1h",
    "durum_mesaji": "Hazır. Zaman dilimi seçip 'Taramayı Başlat' butonuna basın.",
    "sonuclar": [],
    "son_guncelleme": "-"
}

def mfi_hesapla(df, period=14):
    typical_price = (df['high'] + df['low'] + df['close']) / 3
    money_flow = typical_price * df['volume']
    
    diff = typical_price.diff()
    pos_mf = money_flow.where(diff > 0, 0.0)
    neg_mf = money_flow.where(diff < 0, 0.0)
    
    pos_sum = pos_mf.rolling(window=period).sum()
    neg_sum = neg_mf.rolling(window=period).sum()
    
    mfi = 100 - (100 / (1 + (pos_sum / neg_sum)))
    return mfi

def arka_plan_tarayici():
    borsa = ccxt.mexc({'enableRateLimit': True})
    while True:
        if not tarama_durumu["aktif"]:
            time.sleep(1)
            continue
            
        tf = tarama_durumu["zaman_dilimi"]
        tarama_durumu["durum_mesaji"] = f"MEXC ({tf}) verileri çekiliyor..."
        
        try:
            piyasalar = borsa.load_markets()
            tickers = borsa.fetch_tickers()
            semboller = [
                s for s, t in tickers.items()
                if s.endswith('/USDT') and piyasalar[s]['active']
                and t.get('quoteVolume', 0) and t['quoteVolume'] >= 100000
            ]
            
            gecici_sonuclar = []
            toplam = len(semboller)
            
            for idx, sembol in enumerate(semboller, 1):
                if not tarama_durumu["aktif"]:
                    break
                    
                tarama_durumu["durum_mesaji"] = f"[{tf.upper()}] Taranıyor: {idx}/{toplam} ({sembol})"
                
                try:
                    mumlar = borsa.fetch_ohlcv(sembol, timeframe=tf, limit=40)
                    if len(mumlar) < 20:
                        continue
                        
                    df = pd.DataFrame(mumlar, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    df['ema8'] = df['close'].ewm(span=8, adjust=False).mean()
                    df['mfi'] = mfi_hesapla(df, period=14)
                    
                    son_fiyat = df['close'].iloc[-1]
                    son_ema8 = df['ema8'].iloc[-1]
                    son_mfi = df['mfi'].iloc[-1]
                    
                    fark_yuzde = ((son_fiyat - son_ema8) / son_ema8) * 100
                    
                    if fark_yuzde <= -7.0 and son_mfi <= 23.0:
                        coin_adi = sembol.replace('/USDT', '_USDT')
                        gecici_sonuclar.append({
                            'coin': sembol,
                            'link': f"https://mexc.com{coin_adi}",
                            'fiyat': son_fiyat,
                            'ema8': round(son_ema8, 6),
                            'fark': round(fark_yuzde, 2),
                            'mfi': round(son_mfi, 2)
                        })
                        tarama_durumu["sonuclar"] = sorted(gecici_sonuclar, key=lambda x: x['fark'])
                except Exception:
                    continue
            
            if tarama_durumu["aktif"]:
                tarama_durumu["sonuclar"] = sorted(gecici_sonuclar, key=lambda x: x['fark'])
                tarama_durumu["son_guncelleme"] = time.strftime("%H:%M:%S")
                tarama_durumu["durum_mesaji"] = f"Tur tamamlandı ({len(gecici_sonuclar)} coin bulundu). 15 sn sonra tekrar taranacak..."
                time.sleep(15)
                
        except Exception:
            tarama_durumu["durum_mesaji"] = "Bağlantı hatası, tekrar deneniyor..."
            time.sleep(5)

# Bulut sunucusu (Gunicorn) başlarken arka plan thread'ini başlat
threading.Thread(target=arka_plan_tarayici, daemon=True).start()

HTML_SAYFA = """
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MEXC Kripto Tarayıcı</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: #0f172a; color: #f8fafc; margin: 0; padding: 15px; }
        .container { max-width: 1000px; margin: auto; }
        .header { background: #1e293b; padding: 20px; border-radius: 12px; display: flex; flex-wrap: wrap; gap: 15px; align-items: center; justify-content: space-between; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
        h1 { margin: 0; font-size: 20px; color: #38bdf8; }
        .controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
        select, button { padding: 10px 16px; border-radius: 8px; border: none; font-size: 15px; font-weight: bold; cursor: pointer; }
        select { background: #334155; color: white; }
        .btn-start { background: #10b981; color: white; }
        .btn-start:hover { background: #059669; }
        .btn-stop { background: #ef4444; color: white; }
        .btn-stop:hover { background: #dc2626; }
        .status-bar { background: #1e293b; margin-top: 15px; padding: 12px 20px; border-radius: 8px; font-size: 14px; color: #94a3b8; display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; }
        .table-container { overflow-x: auto; margin-top: 20px; border-radius: 12px; }
        table { width: 100%; border-collapse: collapse; background: #1e293b; min-width: 550px; }
        th, td { padding: 14px 16px; text-align: left; border-bottom: 1px solid #334155; }
        th { background: #0284c7; color: white; font-size: 13px; text-transform: uppercase; }
        tr:hover { background: #263349; }
        .badge-red { background: rgba(239, 68, 68, 0.2); color: #f87171; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
        .badge-blue { background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 4px 8px; border-radius: 6px; font-weight: bold; }
        a.coin-link { color: #38bdf8; text-decoration: none; font-weight: bold; }
        a.coin-link:hover { text-decoration: underline; }
    </style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>📊 MEXC Canlı Tarayıcı (EMA 8 ≤ -%7 & MFI ≤ 23)</h1>
        <div class="controls">
            <select id="timeframe">
                <option value="15m">15 Dakika (15m)</option>
                <option value="1h" selected>1 Saat (1h)</option>
                <option value="4h">4 Saat (4h)</option>
                <option value="1d">1 Gün (1d)</option>
            </select>
            <button class="btn-start" onclick="baslat()">▶ Taramayı Başlat</button>
            <button class="btn-stop" onclick="durdur()">⏹ Durdur</button>
        </div>
    </div>

    <div class="status-bar">
        <span id="durum">Hazır.</span>
        <span>Son Tam Tur: <strong id="guncelleme">-</strong></span>
    </div>

    <div class="table-container">
        <table>
            <thead>
                <tr>
                    <th>Coin (MEXC Grafik)</th>
                    <th>Güncel Fiyat</th>
                    <th>EMA 8 Değeri</th>
                    <th>EMA 8 Fark (%)</th>
                    <th>MFI (14)</th>
                </tr>
            </thead>
            <tbody id="tablo-govde">
                <tr><td colspan="5" style="text-align:center; color:#64748b;">Henüz sonuç yok. Taramayı başlatın.</td></tr>
            </tbody>
        </table>
    </div>
</div>

<script>
    function baslat() {
        const tf = document.getElementById('timeframe').value;
        fetch('/baslat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({timeframe: tf})
        });
    }

    function durdur() {
        fetch('/durdur', {method: 'POST'});
    }

    setInterval(() => {
        fetch('/durum')
            .then(r => r.json())
            .then(data => {
                document.getElementById('durum').innerText = data.durum_mesaji;
                document.getElementById('guncelleme').innerText = data.son_guncelleme;
                
                const tbody = document.getElementById('tablo-govde');
                if (data.sonuclar.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:#64748b;">Kriterlere uyan coin bekleniyor...</td></tr>';
                } else {
                    tbody.innerHTML = data.sonuclar.map(c => `
                        <tr>
                            <td><a class="coin-link" href="${c.link}" target="_blank">${c.coin}</a></td>
                            <td>${c.fiyat}</td>
                            <td>${c.ema8}</td>
                            <td><span class="badge-red">${c.fark}%</span></td>
                            <td><span class="badge-blue">${c.mfi}</span></td>
                        </tr>
                    `).join('');
                }
            });
    }, 2000);
</script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_SAYFA)

@app.route('/baslat', methods=['POST'])
def baslat():
    veri = request.get_json()
    tarama_durumu["zaman_dilimi"] = veri.get("timeframe", "1h")
    tarama_durumu["aktif"] = True
    tarama_durumu["durum_mesaji"] = "Tarama başlatılıyor..."
    return jsonify({"status": "ok"})

@app.route('/durdur', methods=['POST'])
def durdur():
    tarama_durumu["aktif"] = False
    tarama_durumu["durum_mesaji"] = "Tarama kullanıcı tarafından durduruldu."
    return jsonify({"status": "ok"})

@app.route('/durum')
def durum():
    return jsonify(tarama_durumu)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
