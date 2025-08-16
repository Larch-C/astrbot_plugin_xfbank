import json
import os
import threading
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register    
from astrbot.api import logger

# 数据持久化相关配置
DATA_FILE = "bank_data.json"
LOCK = threading.Lock()  # 用于线程安全操作

class BankData:
    """银行数据管理类，负责数据的加载、保存和线程安全操作"""
    def __init__(self):
        self.accounts = {}      # {user_id: 余额}
        self.cards = {}         # {user_id: 卡号}
        self.transactions = {}  # {user_id: [交易记录]}
        self.load_data()

    def load_data(self):
        """从文件加载数据"""
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', {})
                    self.cards = data.get('cards', {})
                    self.transactions = data.get('transactions', {})
                logger.info("银行数据加载成功")
            except Exception as e:
                logger.error(f"加载银行数据失败: {str(e)}")

    def save_data(self):
        """保存数据到文件"""
        try:
            with LOCK:
                data = {
                    'accounts': self.accounts,
                    'cards': self.cards,
                    'transactions': self.transactions
                }
                with open(DATA_FILE, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("银行数据保存成功")
        except Exception as e:
            logger.error(f"保存银行数据失败: {str(e)}")

    def add_transaction(self, user_id, transaction_type, amount, target=None):
        """添加交易记录"""
        if user_id not in self.transactions:
            self.transactions[user_id] = []
            
        record = {
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'type': transaction_type,
            'amount': amount,
            'target': target,
            'balance': self.accounts.get(user_id, 0)
        }
        
        self.transactions[user_id].append(record)
        # 只保留最近100条记录
        if len(self.transactions[user_id]) > 100:
            self.transactions[user_id] = self.transactions[user_id][-100:]
        self.save_data()

# 全局银行数据实例
bank_data = BankData()

def generate_card_number(user_id: str) -> str:
    """生成卡号：前缀+用户ID后6位+校验位"""
    user_suffix = str(user_id)[-6:].zfill(6)  # 确保6位，不足补0
    # 简单校验位计算
    check_digit = sum(int(c) for c in user_suffix) % 10
    return f"XF{user_suffix}{check_digit}"

def other_bank_transfer(bank_name: str, target_account: str, amount: int) -> bool:
    """模拟跨行转账接口"""
    logger.info(f"向{bank_name}的账户{target_account}转账{amount}元")
    import time
    time.sleep(0.5)
    return True

@register("xfbank", "YourName", "一个功能完善的虚拟银行插件", "2.0.0")
class BankPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.start_auto_save()

    def start_auto_save(self):
        """启动自动保存数据的定时任务"""
        def auto_save():
            while True:
                bank_data.save_data()
                import time
                time.sleep(300)
        
        thread = threading.Thread(target=auto_save, daemon=True)
        thread.start()

    async def initialize(self):
        logger.info("虚拟银行插件已初始化")

    async def terminate(self):
        bank_data.save_data()
        logger.info("虚拟银行插件已卸载")

    @filter.command("xfbank")
    async def xfbank(self, event: AstrMessageEvent):
        # 只保留命令后的参数
        args = event.message_str.strip().split()
        if args and args[0].lower() == "xfbank":
            args = args[1:]
        logger.info(f"xfbank命令收到参数: {args}")
        user_id = event.get_sender_id()
        
        # 开户命令：/xfbank kaihu
        if len(args) >= 1 and args[0] == "kaihu":
            if user_id in bank_data.cards:
                yield event.plain_result(f"你已开户，卡号为：{bank_data.cards[user_id]}")
                return
                
            # 创建账户
            card_number = generate_card_number(user_id)
            bank_data.cards[user_id] = card_number
            bank_data.accounts[user_id] = 0
            bank_data.add_transaction(user_id, "开户", 0)
            bank_data.save_data()
            
            yield event.plain_result(
                f"开户成功！\n卡号：{card_number}\n"
                f"无需密码，所有操作直接使用命令即可"
            )
            return
    
        yield event.plain_result(
            "虚拟银行命令帮助：\n"
            "/xfbank kaihu - 开户\n"
            "/bank balance - 查询余额\n"
            "/bank deposit <金额> - 存款\n"
            "/bank withdraw <金额> - 取款\n"
            "/bank transfer 本行 <目标卡号> <金额> - 本银行转账\n"
            "/bank transfer <目标银行> <目标账户> <金额> - 跨行转账\n"
            "/bank record [条数] - 查询交易记录（默认10条，最多20条）"
        )

    @filter.command("bank")
    async def bank(self, event: AstrMessageEvent):
        user_id = event.get_sender_id()
        args = event.message_str.strip().split()
        if args and args[0].lower() == "bank":
            args = args[1:]
        # 1. 查询余额：/bank balance
        if len(args) == 1 and args[0] == "balance":
            balance = bank_data.accounts.get(user_id, 0)
            yield event.plain_result(
                f"账户信息：\n"
                f"卡号：{bank_data.cards[user_id]}\n"
                f"当前余额：{balance} 元\n"
                f"查询时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return
            
        # 2. 存款：/bank deposit <金额>
        elif len(args) == 2 and args[0] == "deposit":
            try:
                amount = int(args[1])
                if amount <= 0:
                    yield event.plain_result("存款金额必须为正数")
                    return
                if amount > 100000:
                    yield event.plain_result("单次存款不能超过100000元")
                    return
                bank_data.accounts[user_id] = bank_data.accounts.get(user_id, 0) + amount
                bank_data.add_transaction(user_id, "存款", amount)
                bank_data.save_data()
                yield event.plain_result(
                    f"存款成功！\n"
                    f"存款金额：{amount} 元\n"
                    f"当前余额：{bank_data.accounts[user_id]} 元"
                )
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return
                
        # 3. 取款：/bank withdraw <金额>
        elif len(args) == 2 and args[0] == "withdraw":
            try:
                amount = int(args[1])
                if amount <= 0:
                    yield event.plain_result("取款金额必须为正数")
                    return
                if amount > 50000:
                    yield event.plain_result("单次取款不能超过50000元")
                    return
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance} 元")
                    return
                bank_data.accounts[user_id] = current_balance - amount
                bank_data.add_transaction(user_id, "取款", amount)
                bank_data.save_data()
                yield event.plain_result(
                    f"取款成功！\n"
                    f"取款金额：{amount} 元\n"
                    f"当前余额：{bank_data.accounts[user_id]} 元"
                )
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return
                
        # 4. 本银行转账：/bank transfer 本行 <目标卡号> <金额>
        elif len(args) == 4 and args[0] == "transfer" and args[1] == "本行":
            try:
                target_card = args[2]
                amount = int(args[3])
                if amount <= 0:
                    yield event.plain_result("转账金额必须为正数")
                    return
                if amount > 50000:
                    yield event.plain_result("单次转账不能超过50000元")
                    return
                target_user_id = None
                for uid, card in bank_data.cards.items():
                    if card == target_card:
                        target_user_id = uid
                        break
                if not target_user_id:
                    yield event.plain_result("目标卡号不存在")
                    return
                if target_user_id == user_id:
                    yield event.plain_result("不能向自己转账")
                    return
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance} 元")
                    return
                with LOCK:
                    bank_data.accounts[user_id] = current_balance - amount
                    bank_data.accounts[target_user_id] = bank_data.accounts.get(target_user_id, 0) + amount
                bank_data.add_transaction(user_id, "转账支出", amount, target_card)
                bank_data.add_transaction(target_user_id, "转账收入", amount, bank_data.cards[user_id])
                bank_data.save_data()
                yield event.plain_result(
                    f"向本行卡号 {target_card} 转账成功！\n"
                    f"转账金额：{amount} 元\n"
                    f"当前余额：{bank_data.accounts[user_id]} 元"
                )
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return
                
        # 5. 跨行转账：/bank transfer <目标银行> <目标账户> <金额>
        elif len(args) == 4 and args[0] == "transfer":
            try:
                bank_name = args[1]
                target_account = args[2]
                amount = int(args[3])
                if amount <= 0:
                    yield event.plain_result("转账金额必须为正数")
                    return
                if amount > 50000:
                    yield event.plain_result("单次转账不能超过50000元")
                    return
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance} 元")
                    return
                bank_data.accounts[user_id] = current_balance - amount
                success = other_bank_transfer(bank_name, target_account, amount)
                if success:
                    bank_data.add_transaction(
                        user_id, f"跨行转账至{bank_name}", amount, target_account
                    )
                    bank_data.save_data()
                    yield event.plain_result(
                        f"已成功向{bank_name}的账户{target_account}转账{amount}元。\n"
                        f"当前余额：{bank_data.accounts[user_id]} 元"
                    )
                else:
                    bank_data.accounts[user_id] = current_balance
                    yield event.plain_result("跨行转账失败，请稍后再试")
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return
                
        # 6. 查询交易记录：/bank record [条数]
        elif (len(args) == 1 or len(args) == 2) and args[0] == "record":
            try:
                if len(args) == 2:
                    count = min(int(args[1]), 20)
                else:
                    count = 10
                records = bank_data.transactions.get(user_id, [])
                if not records:
                    yield event.plain_result("暂无交易记录")
                    return
                display_records = records[-count:][::-1]
                result = ["最近交易记录："]
                for idx, record in enumerate(display_records, 1):
                    result.append(
                        f"{idx}. {record['time']} - {record['type']}：{record['amount']}元 "
                        f"{'→ ' + record['target'] if record['target'] else ''} "
                        f"[余额：{record['balance']}元]"
                    )
                yield event.plain_result("\n".join(result))
                return
            except ValueError:
                yield event.plain_result("用法：/bank record [条数]")
                return
                
        yield event.plain_result(
            "银行操作命令帮助：\n"
            "/bank balance - 查询余额\n"
            "/bank deposit <金额> - 存款\n"
            "/bank withdraw <金额> - 取款\n"
            "/bank transfer 本行 <目标卡号> <金额> - 本银行转账\n"
            "/bank transfer <目标银行> <目标账户> <金额> - 跨行转账\n"
            "/bank record [条数] - 查询交易记录（默认10条，最多20条）"
        )
