'''
EMA快线：最近12日平均价格
EMA慢线：最近26日平均价格
DIF线：EMA快线 - EMA慢线
DEA线： 最近十日DIF的均值
MACD线：DIF - DEA （如果为正上涨概率大，为负下跌概率大）
'''

from jqdata import *
import talib

def initialize(context):
    set_param()
    set_backtest()
    # 运行函数
    run_daily(trade, time='every_bar')
    
def set_param():
    g.days=0
    g.refresh_rate=10 # 调仓周期
    
    
def set_backtest():
    set_benchmark('000905.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    log.set_level('order','error')
    
def before_trading_start(context):
    set_slippage(FixedSlippage(0.02))
    set_order_cost(OrderCost(open_tax=0, close_tax=0.001, \
                             open_commission=0.0003, close_commission=0.0003,\
                             close_today_commission=0, min_commission=5), type='stock')

def filter_stocks(stock_list):
    current_data=get_current_data()
    stocks=[stock for stock in stock_list if not current_data[stock].paused and not '退' in current_data[stock].name and not current_data[stock].is_st ]
    
    return stocks

def trade(context):
    if not g.days or g.refresh_rate%10!=0:
        g.days+=1
        return
    # PE：Price to Earnings Ratio，股价/EPS
    # PB: Price to Book ratio，等于股价/每股净资产，用来表明股价是否能体现资产
    # EPS: Earnings Per Share
    # inc_net_profit_annual：净利润同比增长率（年）
    # ROE 是 Return on Equity 的缩写，中文是 净资产收益率, 等于净收入/净资产
    stock_to_choose=get_fundamentals(query(
        valuation.code,valuation.pe_ratio,
        valuation.pb_ratio,valuation.market_cap,
        indicator.eps,indicator.inc_net_profit_annual,
        indicator.roe
        ).filter(
            valuation.pe_ratio<40,
            valuation.pe_ratio>10,
            indicator.eps>0.3,
            indicator.inc_net_profit_annual>0.3,
            indicator.roe>15
            ).order_by(valuation.pb_ratio.asc()).limit(50), date=None)
    stock_codes=filter_stocks(list(stock_to_choose['code']))
    buy_list=[]
    sell_list=[]
    hold_list=list(context.portfolio.positions.keys())
    cash=context.portfolio.available_cash
    log.info("current cash：", cash)
    for stock in stock_codes:
        prices=array(attribute_history(stock, 300, '1d', ['close'])['close'])
        [DIF,DEA,MACD]=talib.MACD(prices,fastperiod=12,slowperiod=26,signalperiod=10)
        if MACD[-1]>0 and MACD[-4]<0:
            buy_list.append(stock)
        if MACD[-1]<0 and MACD[-4]>0:
            sell_list.append(stock)
    for security in sell_list:
        order_target(security, 0)
        log.info("sold", security)
    for security in buy_list:
        order_value(security, cash/len(buy_list))
        log.info("bought ", context.portfolio.positions[security].total_amount, security)
    log.info('curruent holdings: ',context.portfolio.positions)
    g.days+=1
                
    
                             
