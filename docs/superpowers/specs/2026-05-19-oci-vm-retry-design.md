# OCI VM 自动重试创建脚本 — 设计文档

**日期**：2026-05-19  
**状态**：已确认，待实现

---

## 背景

Oracle Cloud Free Tier（Tokyo 区域）的 VM.Standard.A1.Flex（ARM）实例因容量紧张，手动创建时频繁报 `Out of capacity`。需要一个自动重试脚本，持续尝试直到成功，同时支持随时手动中断和重启。

---

## 目标

- 自动轮询 OCI API，每 60 秒尝试一次创建 VM
- 成功后打印公网 IP 并弹出 Windows 通知
- 支持 Ctrl+C 干净退出，重启后从头继续（无需恢复状态）
- 提供双击启动的 `.bat` 文件

---

## 文件结构

```
oci-vm-creator/          ← 独立文件夹，与 Bot 仓库分开
├── create_vm.py         ← 主脚本
└── 启动.bat             ← 双击运行快捷方式
```

---

## 依赖

| 包 | 版本要求 | 用途 |
|---|---|---|
| `oci` | 最新 | Oracle Cloud 官方 Python SDK |
| `winotify` | 最新 | Windows Toast 弹窗通知 |

安装：`pip install oci winotify`

认证通过 `~/.oci/config` 文件，不在代码中存放任何密钥。

---

## VM 配置（目标实例规格）

| 参数 | 值 |
|---|---|
| Shape | VM.Standard.A1.Flex |
| OCPU | 1 |
| Memory | 6 GB |
| Image | Canonical Ubuntu 22.04 |
| Availability Domain | AP-TOKYO-1-AD-1 |
| VCN | vcn-20260515-1839 |
| Subnet | subnet-20260515-1839 |
| SSH 公钥 | 从本地 `.pub` 文件读取（路径在常量块配置） |

---

## 脚本内部结构

### 顶部常量块（用户唯一需要修改的地方）

```python
SSH_KEY_PATH    = r"C:\Users\你的名字\.ssh\id_rsa.pub"
COMPARTMENT_ID  = "ocid1.compartment.oc1..xxxxx"
AD_NAME         = "AP-TOKYO-1-AD-1"
SUBNET_ID       = "ocid1.subnet.oc1..xxxxx"
IMAGE_ID        = "ocid1.image.oc1..xxxxx"   # Ubuntu 22.04 Tokyo 镜像 ID
DISPLAY_NAME    = "fortune-purple-bot"
RETRY_INTERVAL  = 60  # 秒
```

### 函数职责

**`try_create_vm(compute, network, config)`**
- 调用 `ComputeClient.launch_instance()` 发起创建
- 轮询实例状态直到 `RUNNING`
- 返回实例的公网 IP（通过 VNIC 查询）
- 若 API 抛出异常，向上传播

**`notify_success(ip)`**
- 在终端打印公网 IP
- 调用 `winotify` 发送 Windows Toast 通知

**`main()`**
- 初始化 OCI config 和 ComputeClient
- 循环调用 `try_create_vm()`
- 捕获 `KeyboardInterrupt`：打印重试次数后干净退出
- 捕获 OCI `ServiceError`：
  - `Out of capacity` → 打印日志，sleep 60s，继续
  - 其他错误 → 打印错误详情，sleep 60s，继续（不崩溃）

### 日志格式

```
[2026-05-19 14:32:01] 第 23 次尝试...
[2026-05-19 14:32:03] 容量不足，60 秒后重试
[2026-05-19 14:33:03] 第 24 次尝试...
[2026-05-19 14:33:10] 成功！公网 IP: 140.83.xx.xx
```

---

## 错误处理策略

| 错误类型 | 处理方式 |
|---|---|
| `Out of capacity`（ServiceError，HTTP 500） | 等待 60 秒，继续重试 |
| 其他 OCI API 错误（网络超时、权限不足等） | 打印错误详情，等待 60 秒，继续重试 |
| `KeyboardInterrupt`（Ctrl+C） | 打印"已停止，共重试 N 次"，退出码 0 |

---

## OCI Config 配置（一次性准备）

文件位置：`~/.oci/config`（Windows 下为 `C:\Users\你的名字\.oci\config`）

```ini
[DEFAULT]
user=ocid1.user.oc1..xxxxx
fingerprint=xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx:xx
tenancy=ocid1.tenancy.oc1..xxxxx
region=ap-tokyo-1
key_file=C:\Users\你的名字\.oci\oci_api_key.pem
```

### 各字段获取方式

| 字段 | 操作路径 |
|---|---|
| `user` | 控制台右上角头像 → My Profile → 复制 OCID |
| `tenancy` | 控制台右上角头像 → Tenancy: xxx → 复制 OCID |
| `region` | 固定填 `ap-tokyo-1` |
| `fingerprint` + `key_file` | My Profile → API Keys → Add API Key → 下载私钥（`.pem`）→ 系统自动显示 fingerprint |

### IMAGE_ID 获取方式

控制台 → Compute → Images → Platform Images → 搜索 "Canonical Ubuntu 22.04" → 选 aarch64（ARM）版本 → 复制 OCID

---

## 使用流程

1. `pip install oci winotify`
2. 配置 `~/.oci/config`
3. 修改 `create_vm.py` 顶部常量
4. 双击 `启动.bat` 或终端运行 `python create_vm.py`
5. 等待弹窗通知

---

## 超出本次范围

- 多可用域轮询（当前仅 AD-1）
- 断点续传（成功后自动配置服务器）
- 图形界面
