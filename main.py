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
        self.passwords = {}     # {user_id: 密码哈希} 实际应用中应使用加密哈希
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
                    self.passwords = data.get('passwords', {})
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
                    'passwords': self.passwords,
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

def verify_password(user_id: str, password: str) -> bool:
    """验证密码（实际应用中应使用加密哈希验证）"""
    stored_password = bank_data.passwords.get(user_id)
    return stored_password == password  # 简化处理，实际应使用哈希比较

def other_bank_transfer(bank_name: str, target_account: str, amount: int) -> bool:
    """模拟跨行转账接口"""
    logger.info(f"向{bank_name}的账户{target_account}转账{amount}元")
    # 模拟网络请求延迟
    import time
    time.sleep(0.5)
    return True  # 实际应用中应根据真实接口返回结果

@register("xfbank", "YourName", "一个功能完善的虚拟银行插件", "2.0.0")
class BankPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 启动定期保存数据的任务（每5分钟）
        self.start_auto_save()

    def start_auto_save(self):
        """启动自动保存数据的定时任务"""
        def auto_save():
            while True:
                bank_data.save_data()
                # 每5分钟保存一次
                import time
                time.sleep(300)
        
        thread = threading.Thread(target=auto_save, daemon=True)
        thread.start()

    async def initialize(self):
        logger.info("虚拟银行插件已初始化")

    async def terminate(self):
        bank_data.save_data()  # 退出时保存数据
        logger.info("虚拟银行插件已卸载")

    @filter.command("xfbank")
    async def xfbank(self, event: AstrMessageEvent):
        """处理开户相关命令"""
        user_id = event.get_sender_id()
        args = event.message_str.strip().split()
        
        # 开户命令：/xfbank kaihu <密码>
        if len(args) >= 1 and args[0] == "kaihu":
            if user_id in bank_data.cards:
                yield event.plain_result(f"你已开户，卡号为：{bank_data.cards[user_id]}")
                return
                
            if len(args) != 2:
                yield event.plain_result("开户命令需要设置密码，用法：/xfbank kaihu <密码>")
                return
                
            password = args[1]
            if len(password) < 6:
                yield event.plain_result("密码长度不能少于6位")
                return
                
            # 创建账户
            card_number = generate_card_number(user_id)
            bank_data.cards[user_id] = card_number
            bank_data.accounts[user_id] = 0  # 初始余额0
            bank_data.passwords[user_id] = password  # 实际应用中应存储哈希值
            bank_data.add_transaction(user_id, "开户", 0)
            bank_data.save_data()
            
            yield event.plain_result(
                f"开户成功！\n卡号：{card_number}\n"
                f"请妥善保管你的密码，后续操作需要验证密码"
            )
            return
        
        # 修改密码：/xfbank changepwd <旧密码> <新密码>
        elif len(args) == 3 and args[0] == "changepwd":
            if user_id not in bank_data.cards:
                yield event.plain_result("请先开户，发送 /xfbank kaihu <密码>")
                return
                
            old_pwd, new_pwd = args[1], args[2]
            if not verify_password(user_id, old_pwd):
                yield event.plain_result("旧密码不正确")
                return
                
            if len(new_pwd) < 6:
                yield event.plain_result("新密码长度不能少于6位")
                return
                
            bank_data.passwords[user_id] = new_pwd
            bank_data.add_transaction(user_id, "修改密码", 0)
            bank_data.save_data()
            yield event.plain_result("密码修改成功")
            return
            
        # 命令帮助
        yield event.plain_result(
            "虚拟银行命令帮助：\n"
            "/xfbank kaihu <密码> - 开户并设置密码\n"
            "/xfbank changepwd <旧密码> <新密码> - 修改密码"
        )

    @filter.command("bank")
    async def bank(self, event: AstrMessageEvent):
        """处理核心银行业务命令"""
        user_id = event.get_sender_id()
        
        # 检查是否已开户
        if user_id not in bank_data.cards:
            yield event.plain_result("请先开户，发送 /xfbank kaihu <密码>")
            return
            
        args = event.message_str.strip().split()
        
        # 1. 查询余额：/bank balance <密码>
        if len(args) == 2 and args[0] == "balance":
            password = args[1]
            if not verify_password(user_id, password):
                yield event.plain_result("密码错误")
                return
                
            balance = bank_data.accounts.get(user_id, 0)
            yield event.plain_result(
                f"账户信息：\n"
                f"卡号：{bank_data.cards[user_id]}\n"
                f"当前余额：{balance} 元\n"
                f"查询时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return
            
        # 2. 存款：/bank deposit <金额> <密码>
        elif len(args) == 3 and args[0] == "deposit":
            try:
                amount = int(args[1])
                password = args[2]
                
                if not verify_password(user_id, password):
                    yield event.plain_result("密码错误")
                    return
                    
                if amount <= 0:
                    yield event.plain_result("存款金额必须为正数")
                    return
                    
                # 限制单次存款上限
                if amount > 100000:
                    yield event.plain_result("单次存款不能超过100000元")
                    return
                    
                # 更新余额
                bank_data.accounts[user_id] = bank_data.accounts.get(user_id, 0) + amount
                bank_data.add_transaction(user_id, "存款", amount)
                bank_data.save_data()
                
                yield event.plain_result(
                    f"存款成功！\n"
                    f"存款成功！\n"
                    f"存款金额：{amount} 元\n"
                    f"当前余额：{bank_data.accounts[user_id]} 元"
                )
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return
                
        # 3. 取款：/bank withdraw <金额> <密码>
        elif len(args) == 3 and args[0] == "withdraw":
            try:
                amount = int(args[1])
                password = args[2]
                
                if not verify_password(user_id, password):
                    yield event.plain_result("密码错误")
                    return
                    
                if amount <= 0:
                    yield event.plain_result("取款金额必须为正数")
                    return
                    
                # 限制单次取款上限
                if amount > 50000:
                    yield event.plain_result("单次取款不能超过50000元")
                    return
                    
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance} 元")
                    return
                    
                # 更新余额
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
                
        # 4. 本银行转账：/bank transfer 本行 <目标卡号> <金额> <密码>
        elif len(args) == 5 and args[0] == "transfer" and args[1] == "本行":
            try:
                target_card = args[2]
                amount = int(args[3])
                password = args[4]
                
                if not verify_password(user_id, password):
                    yield event.plain_result("密码错误")
                    return
                    
                if amount <= 0:
                    yield event.plain_result("转账金额必须为正数")
                    return
                    
                # 限制单次转账上限
                if amount > 50000:
                    yield event.plain_result("单次转账不能超过50000元")
                    return
                    
                # 查找目标用户ID
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
                    
                # 执行转账
                with LOCK:  # 确保转账操作的原子性
                    bank_data.accounts[user_id] = current_balance - amount
                    bank_data.accounts[target_user_id] = bank_data.accounts.get(target_user_id, 0) + amount
                
                # 记录交易
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
                
        # 5. 跨行转账：/bank transfer <目标银行> <目标账户> <金额> <密码>
        elif len(args) == 5 and args[0] == "transfer":
            try:
                bank_name = args[1]
                target_account = args[2]
                amount = int(args[3])
                password = args[4]
                
                if not verify_password(user_id, password):
                    yield event.plain_result("密码错误")
                    return
                    
                if amount <= 0:
                    yield event.plain_result("转账金额必须为正数")
                    return
                    
                # 限制单次转账上限
                if amount > 50000:
                    yield event.plain_result("单次转账不能超过50000元")
                    return
                    
                current_balance = bank_data.accounts.get(user_id, 0)
                if current_balance < amount:
                    yield event.plain_result(f"余额不足！当前余额：{current_balance} 元")
                    return
                    
                # 扣减余额
                bank_data.accounts[user_id] = current_balance - amount
                
                # 调用跨行转账接口
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
                    # 转账失败回滚
                    bank_data.accounts[user_id] = current_balance
                    yield event.plain_result("跨行转账失败，请稍后再试")
                return
            except ValueError:
                yield event.plain_result("请输入正确的金额数字")
                return
                
        # 6. 查询交易记录：/bank record [条数] <密码>
        elif (len(args) == 2 or len(args) == 3) and args[0] == "record":
            try:
                # 解析参数
                if len(args) == 3:
                    count = min(int(args[1]), 20)  # 最多显示20条
                    password = args[2]
                else:
                    count = 10  # 默认显示10条
                    password = args[1]
                    
                if not verify_password(user_id, password):
                    yield event.plain_result("密码错误")
                    return
                    
                records = bank_data.transactions.get(user_id, [])
                if not records:
                    yield event.plain_result("暂无交易记录")
                    return
                    
                # 取最近的count条记录
                display_records = records[-count:][::-1]  # 倒序显示，最新的在前
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
                yield event.plain_result("用法：/bank record [条数] <密码>")
                return
                
        # 命令帮助
        yield event.plain_result(
            "银行操作命令帮助：\n"
            "/bank balance <密码> - 查询余额\n"
            "/bank deposit <金额> <密码> - 存款\n"
            "/bank withdraw <金额> <密码> - 取款\n"
            "/bank transfer 本行 <目标卡号> <金额> <密码> - 本银行转账\n"
            "/bank transfer <目标银行> <目标账户> <金额> <密码> - 跨行转账\n"
            "/bank record [条数] <密码> - 查询交易记录（默认10条，最多20条）"
        )
