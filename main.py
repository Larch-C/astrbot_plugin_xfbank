import json
import os
import threading
import random
from datetime import datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register    
from astrbot.api import logger
import asyncio
from astrbot.api.star import StarTools

# 数据持久化相关配置
LOCK = threading.Lock()  # 用于线程安全操作

class BankData:
    """银行数据管理类，负责数据的加载、保存和线程安全操作"""
    def __init__(self):
        self.data_dir = StarTools.get_data_dir("xfbank")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.data_file = self.data_dir / "bank_data.json"
        self.accounts = {}      # {user_id: 余额}
        self.cards = {}         # {user_id: 卡号}
        self.transactions = {}  # {user_id: [交易记录]}
        self.last_checkin = {}  # {user_id: 上次签到日期}
        self.card_to_user = {}  # {卡号: user_id}
        self.load_data()

    def load_data(self):
        """从文件加载数据"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.accounts = data.get('accounts', {})
                    self.cards = data.get('cards', {})
                    self.transactions = data.get('transactions', {})
                    self.last_checkin = data.get('last_checkin', {})
                    # 构建卡号反查索引
                    self.card_to_user = {v: k for k, v in self.cards.items()}
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
                    'transactions': self.transactions,
                    'last_checkin': self.last_checkin
                }
                with open(self.data_file, 'w', encoding='utf-8') as f:
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
        # 不再立即保存数据

# 全局银行数据实例
bank_data = BankData()

def generate_card_number(user_id: str) -> str:
    """生成唯一卡号：X+四位数字，不重复"""
    existing_cards = set(bank_data.cards.values())
    while True:
        number = f"X{random.randint(1000, 9999)}"
        if number not in existing_cards:
            return number

async def other_bank_transfer(bank_name: str, target_account: str, amount: float) -> bool:
    """模拟跨行转账接口"""
    logger.info(f"向{bank_name}的账户{target_account}转账{amount}元")
    await asyncio.sleep(0.5)
    return True

@register("xfbank", "YourName", "一个功能完善的虚拟银行插件", "2.0.0")
class BankPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.auto_save_task = None

    async def initialize(self):
        logger.info("虚拟银行插件已初始化")
        self.auto_save_task = asyncio.create_task(self.auto_save())

    async def terminate(self):
        bank_data.save_data()
        logger.info("虚拟银行插件已卸载")
        if self.auto_save_task:
            self.auto_save_task.cancel()

    async def auto_save(self):
        while True:
            bank_data.save_data()
            await asyncio.sleep(300)

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
            bank_data.card_to_user[card_number] = user_id
            bank_data.accounts[user_id] = 0
            bank_data.add_transaction(user_id, "开户", 0)
            bank_data.save_data()
            
            yield event.plain_result(
                f"开户成功！\n卡号：{card_number}\n"
                f"无需密码，所有操作直接使用命令即可"
            )
            return
    
        yield event.plain_result(
       "银行操作命令帮助：\n"
       "银行操作命令帮助：\n"
       "/bank chaxun - 查询余额\n"
       "/bank qiandao - 每日签到（100~500元，含小数）\n"
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

        # 1. 查询余额：/bank chaxun
        if len(args) == 1 and args[0] == "chaxun":
            balance = bank_data.accounts.get(user_id, 0)
            yield event.plain_result(
                f"账户信息：\n"
                f"卡号：{bank_data.cards.get(user_id, '未开户')}\n"
                f"当前余额：{balance:.2f} 元\n"
                f"查询时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        # 2. 签到：/bank qiandao
        elif len(args) == 1 and args[0] == "qiandao":
            if user_id not in bank_data.cards:
                yield event.plain_result("请先开户，发送 /xfbank kaihu")
                return
            today = datetime.now().strftime("%Y-%m-%d")
            last = bank_data.last_checkin.get(user_id, "")
            if last == today:
                yield event.plain_result("今天已签到，请勿重复签到。")
                return
            amount = round(random.uniform(100, 500), 2)
            bank_data.accounts[user_id] = round(bank_data.accounts.get(user_id, 0) + amount, 2)
            bank_data.last_checkin[user_id] = today
            bank_data.add_transaction(user_id, "每日签到", amount)
            bank_data.save_data()
            yield event.plain_result(
                f"签到成功，余额增加{amount:.2f}元，账户余额为{bank_data.accounts[user_id]:.2f}元"
            )
            return

        # 3. 本银行转账：/bank transfer 本行 <目标卡号> <金额>
        elif len(args) == 4 and args[0] == "transfer" and args[1] == "本行":
            target_card = args[2]
            try:
                amount = round(float(args[3]), 2)
                if amount <= 0:
                    yield event.plain_result("转账金额必须为正数")
                    return
                target_user_id = bank_data.card_to_user.get(target_card)
                if not target_user_id:
                    yield event.plain_result("目标卡号不存在")
                    return
                if target_user_id == user_id:
                    yield event.plain_result("不能向自己转账")
                    return
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance:.2f} 元")
                    return
                with LOCK:
                    bank_data.accounts[user_id] = round(current_balance - amount, 2)
                    bank_data.accounts[target_user_id] = round(bank_data.accounts.get(target_user_id, 0) + amount, 2)
                bank_data.add_transaction(user_id, "转账支出", amount, target_card)
                bank_data.add_transaction(target_user_id, "转账收入", amount, bank_data.cards[user_id])
                bank_data.save_data()
                yield event.plain_result(
                    f"向本行卡号 {target_card} 转账成功！\n"
                    f"转账金额：{amount:.2f} 元\n"
                    f"当前余额：{bank_data.accounts[user_id]:.2f} 元"
                )
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return

        # 4. 跨行转账：/bank transfer <目标银行> <目标账户> <金额>
        elif len(args) == 4 and args[0] == "transfer":
            bank_name = args[1]
            target_account = args[2]
            try:
                amount = round(float(args[3]), 2)
                if amount <= 0:
                    yield event.plain_result("转账金额必须为正数")
                    return
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance:.2f} 元")
                    return
                bank_data.accounts[user_id] = round(current_balance - amount, 2)
                success = await other_bank_transfer(bank_name, target_account, amount)
                if success:
                    bank_data.add_transaction(
                        user_id, f"跨行转账至{bank_name}", amount, target_account
                    )
                    bank_data.save_data()
                    yield event.plain_result(
                        f"已成功向{bank_name}的账户{target_account}转账{amount:.2f}元。\n"
                        f"当前余额：{bank_data.accounts[user_id]:.2f} 元"
                    )
                else:
                    bank_data.accounts[user_id] = current_balance
                    yield event.plain_result("跨行转账失败，请稍后再试")
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return

        # 5. 查询交易记录：/bank record [条数]
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
                        f"{idx}. {record['time']} - {record['type']}：{float(record['amount']):.2f}元 "
                        f"{'→ ' + str(record['target']) if record['target'] else ''} "
                        f"[余额：{float(record['balance']):.2f}元]"
                    )
                yield event.plain_result("\n".join(result))
                return
            except ValueError:
                yield event.plain_result("用法：/bank record [条数]")
                return

        # 命令帮助
        yield event.plain_result(
            "银行操作命令帮助：\n"
            "/bank chaxun - 查询余额\n"
            "/bank qiandao - 每日签到（100~500元，含小数）\n"
            "/bank transfer 本行 <目标卡号> <金额> - 本银行转账\n"
            "/bank transfer <目标银行> <目标账户> <金额> - 跨行转账\n"
            "/bank record [条数] - 查询交易记录（默认10条，最多20条）"
        )
