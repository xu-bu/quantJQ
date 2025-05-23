# 导入函数库
from jqdata import *

# 初始化函数，设定基准等等
def initialize(context):
    # 设定沪深300作为基准
    set_benchmark('000300.XSHG')
    # 开启动态复权模式(真实价格)
    set_option('use_real_price', True)
    # 输出内容到日志 log.info()
    log.info('初始函数开始运行且全局只运行一次')
    # 过滤掉order系列API产生的比error级别低的log
    log.set_level('order','error')
    
    context.buy_list = []
    context.hold_days = {}  # 记录持仓时间
    context.stock_limit = 5

    ### 股票相关设定 ###
    # 股票类每笔交易时的手续费是：买入时佣金万分之三，卖出时佣金万分之三加千分之一印花税, 每笔交易佣金最低扣5块钱
    set_order_cost(OrderCost(close_tax=0.001, open_commission=0.0003, close_commission=0.0003, min_commission=5), type='stock')
   
    ## 运行函数（reference_security为运行时间的参考标的；传入的标的只做种类区分，因此传入'000300.XSHG'或'510300.XSHG'是一样的）
      # 开盘前运行
    run_daily(before_market_open, time='before_open', reference_security='000300.XSHG')
      # 开盘时运行
    run_daily(market_open, time='open', reference_security='000300.XSHG')

## 开盘前运行函数
def before_market_open(context):
    stock_to_choose=get_fundamentals(query(
        valuation.code,valuation.pe_ratio,
        valuation.pb_ratio,valuation.market_cap,
        indicator.eps,indicator.inc_net_profit_annual,
        indicator.roe
        ).filter(
            indicator.inc_net_profit_annual > 0.1
            ).order_by(valuation.pb_ratio.asc()), date=None)
    stock_codes=list(stock_to_choose['code'])
    stock_codes=[code for code in stock_codes if is_first_limit_up(context, code)]
    context.buy_list = stock_codes

def is_first_limit_up(context, stock,  window=5):
    """
    判断昨天是否是首次涨停（前几天没有涨停）
    """
    hist = get_price(stock, count=window, frequency='1d')
    if len(hist) < window:
        return False
    # 前几天不能有涨停
    for i in range(window - 1):
        if hist.iloc[i]['close'] == hist.iloc[i]['high']:
            return False
            
    yesterday = hist.iloc[-1]
    # 昨天必须是涨停
    if yesterday['close'] == yesterday['high']:
        return True
    return False

## 开盘时运行函数
def market_open(context):
    """
    1. 买入逻辑：
        - 选出“首板”(昨天首次涨停)个股；
        - 如果未开盘即涨停（即一字板），则跳过；
        - 持仓最多 context.stock_limit 个股票；
        - 每只股票买入等权重；
        - 买入后记录该股票持仓天数为 0；
    
    2. 卖出逻辑：
        - 如果持仓时间 ≥ 2 天或者亏损大于5%，则卖出；
        - 卖出后删除持仓时间记录。
    """
    buy_list=get_filtered_stocks(context,context.buy_list)
    max_positions = context.stock_limit
    for stock in context.hold_days:
        context.hold_days[stock]+=1
    # === 1. 买入逻辑 ===
    for stock in buy_list:
        if len(context.portfolio.positions.keys()) >=max_positions:
            break
        if stock in context.portfolio.positions.keys():
            continue
        context.hold_days[stock] = 0
        log.info(f"【买入】首板股：{stock}")
    stock_count=len(context.hold_days)    
    if not stock_count: return
    
    # 需要买入新的股票，调整仓位，均衡持仓
    if stock_count>len(context.portfolio.positions.keys()):
        for stock in context.hold_days.keys():
            total_value = context.portfolio.total_value
            target_value = total_value / stock_count  # 每只股票均衡持仓金额
            current_data = get_current_data()
            for stock in context.hold_days:
                if not current_data[stock].paused and current_data[stock].last_price > 0:
                    order_value(stock, target_value)
    log.info("after buy")
    log.info(context.portfolio.positions)
    # === 2. 卖出逻辑 ===
    for stock in context.portfolio.positions.keys():
        price = get_current_tick(stock)['current']
        cost = context.portfolio.positions[stock].avg_cost
        
        if stock not in context.hold_days:
            order_target(stock, 0)
        # 条件 1：止损
        elif price < cost * 0.95:
            order_target(stock, 0)
            log.info(f"【卖出】{stock} 触发止损")
            context.hold_days.pop(stock)
        # 条件 2：持仓超过2天
        elif context.hold_days[stock] > 2:
            order_target(stock, 0)
            log.info(f"【卖出】{stock} 持仓超过2天")
            context.hold_days.pop(stock)
    
def is_new_stock(context,stock_code, n=60):
    start_date = get_security_info(stock_code).start_date
    today = context.current_dt.date()
    n_days_ago = get_trade_days(end_date=today, count=n)[0]

    return (today - start_date).days <= n

# n为次新股时限
def get_filtered_stocks(context,stock_codes,n=60):
    all_stock_codes = get_all_securities('stock', context.current_dt).index.tolist()
    current_data=get_current_data()
    stock_codes = [stock for stock in stock_codes if not (
            (current_data[stock].day_open == current_data[stock].high_limit) or   # 涨停开盘
            (current_data[stock].day_open == current_data[stock].low_limit) or    # 跌停开盘
            current_data[stock].paused or  # 停牌
            current_data[stock].is_st or   # ST
            ('ST' in current_data[stock].name) or
            ('*' in current_data[stock].name) or
            ('退' in current_data[stock].name) or
            (stock.startswith('300')) or    # 创业
            (stock.startswith('688')) or  # 科创
            is_new_stock(context,stock) # 次新股
    )]
    return stock_codes

