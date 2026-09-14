import asyncio
from mt5_bridge import init_mt5, get_candles
from strategy.smc import analyze_symbol


async def main():
    init_mt5()
    
    print("=" * 90)
    print(f"{'Symbol':10} {'BOS_B':6} {'BOS_S':6} {'CH_B':6} {'CH_S':6} {'ADX':6} {'HTF':5} {'Score':6} {'Signal':7}")
    print("=" * 90)
    
    for sym in ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD']:
        candles = get_candles(sym, 'H1', 200)
        if not candles or len(candles) < 60:
            print(f"{sym:10} -- not enough candles")
            continue
        
        r = analyze_symbol(sym, candles)
        ind = r.indicators
        
        bos_b = ind.get('bos_bull', False)
        bos_s = ind.get('bos_bear', False)
        ch_b = ind.get('choch_bull', False)
        ch_s = ind.get('choch_bear', False)
        adx = ind.get('adx', 0)
        conf = r.confidence
        sig = r.signal or '-'
        
        # حساب htf
        price = r.price
        ema50 = ind.get('ema50', 0)
        htf = 'UP' if price > ema50 else 'DN'
        
        print(f"{sym:10} {str(bos_b):6} {str(bos_s):6} {str(ch_b):6} {str(ch_s):6} {adx:6.1f} {htf:5} {conf:6.3f} {sig:7}")
    
    print("=" * 90)


if __name__ == "__main__":
    asyncio.run(main())