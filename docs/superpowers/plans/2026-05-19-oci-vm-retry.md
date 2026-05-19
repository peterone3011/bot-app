# OCI VM 自动重试脚本 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 写一个 Python 脚本，每 60 秒尝试在 Oracle Cloud Tokyo 区域创建 ARM VM，直到成功，成功后打印公网 IP 并弹出 Windows 通知。

**Architecture:** 单文件脚本 + bat 启动器，放在独立文件夹 `oci-vm-creator/`。顶部常量块存放所有用户配置，三个函数分别负责创建实例、查询 IP、通知成功，`main()` 管理重试循环和错误处理。

**Tech Stack:** Python 3, `oci` (Oracle Cloud SDK), `winotify` (Windows Toast 通知)

---

## 文件结构

| 文件 | 职责 |
|---|---|
| `oci-vm-creator/create_vm.py` | 主脚本：常量配置 + 重试逻辑 + OCI API 调用 |
| `oci-vm-creator/requirements.txt` | 依赖声明 |
| `oci-vm-creator/启动.bat` | 双击启动快捷方式 |

---

### Task 1: 创建项目文件夹和依赖文件

**Files:**
- Create: `oci-vm-creator/requirements.txt`

- [ ] **Step 1: 在 E:\ 下创建独立文件夹**

```
mkdir E:\oci-vm-creator
```

- [ ] **Step 2: 写 requirements.txt**

内容如下，保存到 `E:\oci-vm-creator\requirements.txt`：

```
oci
winotify
```

- [ ] **Step 3: 安装依赖**

```
pip install oci winotify
```

预期输出：Successfully installed oci-... winotify-... 等，无报错。

- [ ] **Step 4: 验证安装**

```
python -c "import oci; import winotify; print('OK')"
```

预期输出：`OK`

---

### Task 2: 写主脚本 create_vm.py

**Files:**
- Create: `oci-vm-creator/create_vm.py`

- [ ] **Step 1: 写完整脚本**

保存以下内容到 `E:\oci-vm-creator\create_vm.py`：

```python
import oci
import time
import sys
from datetime import datetime

# ── 配置区域（只需修改这里）─────────────────────────────────────
# SSH 公钥路径（.pub 文件）
SSH_KEY_PATH   = r"C:\Users\你的名字\.ssh\id_rsa.pub"

# Compartment OCID：控制台右上角头像 → Tenancy → Compartments
# 如果用根 Compartment，就填 Tenancy OCID
COMPARTMENT_ID = "ocid1.tenancy.oc1..xxxxx"

# 可用域（Tokyo 只有 AD-1）
AD_NAME        = "AP-TOKYO-1-AD-1"

# Subnet OCID：控制台 → Networking → Virtual Cloud Networks
# → vcn-20260515-1839 → Subnets → subnet-20260515-1839 → 复制 OCID
SUBNET_ID      = "ocid1.subnet.oc1.ap-tokyo-1.xxxxx"

# Ubuntu 22.04 aarch64 镜像 OCID：
# 控制台 → Compute → Images → Platform Images
# 搜索 "Canonical Ubuntu" → 选 aarch64 版本 → 复制 OCID
IMAGE_ID       = "ocid1.image.oc1.ap-tokyo-1.xxxxx"

# VM 显示名称（随意填）
DISPLAY_NAME   = "fortune-purple-bot"

# 重试间隔（秒）
RETRY_INTERVAL = 60
# ─────────────────────────────────────────────────────────────


def log(msg):
    """带时间戳打印，立即刷新（不缓冲）"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def get_public_ip(compute, network, instance_id):
    """查询实例的公网 IP（通过 VNIC）"""
    attachments = compute.list_vnic_attachments(
        compartment_id=COMPARTMENT_ID,
        instance_id=instance_id
    ).data
    for att in attachments:
        vnic = network.get_vnic(att.vnic_id).data
        if vnic.public_ip:
            return vnic.public_ip
    return "(未分配公网 IP)"


def try_create_vm(compute, network):
    """
    发起一次创建请求，轮询直到 RUNNING，返回公网 IP。
    失败时向上抛出异常，由 main() 处理重试。
    """
    with open(SSH_KEY_PATH, "r") as f:
        ssh_key = f.read().strip()

    launch_details = oci.core.models.LaunchInstanceDetails(
        availability_domain=AD_NAME,
        compartment_id=COMPARTMENT_ID,
        display_name=DISPLAY_NAME,
        image_id=IMAGE_ID,
        subnet_id=SUBNET_ID,
        shape="VM.Standard.A1.Flex",
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=1,
            memory_in_gbs=6
        ),
        metadata={"ssh_authorized_keys": ssh_key},
        create_vnic_details=oci.core.models.CreateVnicDetails(
            assign_public_ip=True,
            subnet_id=SUBNET_ID
        )
    )

    response = compute.launch_instance(launch_details)
    instance_id = response.data.id
    log(f"请求已提交，实例 ID: {instance_id}")
    log("轮询实例状态，等待 RUNNING...")

    while True:
        state = compute.get_instance(instance_id).data.lifecycle_state
        if state == "RUNNING":
            break
        log(f"当前状态: {state}，10 秒后再查...")
        time.sleep(10)

    ip = get_public_ip(compute, network, instance_id)
    return ip


def notify_success(ip):
    """终端打印 + Windows Toast 弹窗"""
    log(f"成功！公网 IP: {ip}")
    try:
        from winotify import Notification
        toast = Notification(
            app_id="OCI VM Creator",
            title="VM 创建成功！",
            msg=f"公网 IP: {ip}",
            duration="long"
        )
        toast.show()
    except Exception as e:
        log(f"(弹窗发送失败: {e}，但 VM 已成功创建，IP 见上方)")


def main():
    config = oci.config.from_file()  # 读取 ~/.oci/config
    compute = oci.core.ComputeClient(config)
    network = oci.core.VirtualNetworkClient(config)

    attempt = 0
    log("OCI VM 自动重试脚本已启动（Ctrl+C 可随时停止）")
    log(f"目标：{DISPLAY_NAME} | Shape: VM.Standard.A1.Flex | 1 OCPU / 6 GB")
    log("-" * 60)

    try:
        while True:
            attempt += 1
            log(f"第 {attempt} 次尝试...")
            try:
                ip = try_create_vm(compute, network)
                notify_success(ip)
                break  # 成功，退出循环
            except oci.exceptions.ServiceError as e:
                if "Out of host capacity" in (e.message or ""):
                    log(f"容量不足，{RETRY_INTERVAL} 秒后重试")
                else:
                    log(f"OCI 错误 (HTTP {e.status} / {e.code}): {e.message}")
                    log(f"{RETRY_INTERVAL} 秒后重试")
                time.sleep(RETRY_INTERVAL)
            except Exception as e:
                log(f"未知错误: {e}")
                log(f"{RETRY_INTERVAL} 秒后重试")
                time.sleep(RETRY_INTERVAL)
    except KeyboardInterrupt:
        log(f"")
        log(f"已手动停止，共尝试 {attempt} 次。")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 将常量改为你的真实值**

打开 `create_vm.py`，修改顶部常量区域（共 6 个值）：

| 常量 | 去哪找 |
|---|---|
| `SSH_KEY_PATH` | 你本地 `id_rsa.pub` 的实际路径 |
| `COMPARTMENT_ID` | 控制台头像 → Tenancy → 复制 OCID（根 Compartment） |
| `SUBNET_ID` | Networking → VCN → subnet-20260515-1839 → 复制 OCID |
| `IMAGE_ID` | Compute → Images → Platform Images → Ubuntu 22.04 aarch64 → 复制 OCID |
| `DISPLAY_NAME` | 随意，比如 `"fortune-purple-bot"` |
| `RETRY_INTERVAL` | 保持 `60` 即可 |

---

### Task 3: 写 启动.bat

**Files:**
- Create: `oci-vm-creator/启动.bat`

- [ ] **Step 1: 写 bat 文件**

保存以下内容到 `E:\oci-vm-creator\启动.bat`（注意编码用 ANSI 或 UTF-8 with BOM）：

```bat
@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo  OCI VM 自动重试创建脚本
echo ============================================
python create_vm.py
echo.
echo 脚本已结束，按任意键关闭窗口...
pause >nul
```

> `%~dp0` 让 bat 始终在脚本所在目录运行，无论从哪里双击。  
> `pause >nul` 保留窗口，让你看到最终 IP。

---

### Task 4: 配置 ~/.oci/config（一次性操作）

**Files:**
- Create: `C:\Users\你的名字\.oci\config`
- Create: `C:\Users\你的名字\.oci\oci_api_key.pem`（从控制台下载）

- [ ] **Step 1: 生成 API Key**

1. 登录 [Oracle Cloud 控制台](https://cloud.oracle.com)
2. 右上角头像 → **My Profile**
3. 左侧菜单 → **API Keys** → **Add API Key**
4. 选 **Generate API Key Pair** → 点 **Download Private Key**，保存为 `oci_api_key.pem`
5. 把 `oci_api_key.pem` 放到 `C:\Users\你的名字\.oci\` 文件夹
6. 对话框里复制 **fingerprint**（格式：`xx:xx:xx:...`）

- [ ] **Step 2: 复制 User OCID 和 Tenancy OCID**

- **User OCID**：右上角头像 → My Profile → 页面顶部 OCID → 点复制
- **Tenancy OCID**：右上角头像 → Tenancy: xxxx → 页面顶部 OCID → 点复制

- [ ] **Step 3: 创建 config 文件**

新建文件 `C:\Users\你的名字\.oci\config`，内容：

```ini
[DEFAULT]
user=ocid1.user.oc1..你的UserOCID
fingerprint=你的fingerprint
tenancy=ocid1.tenancy.oc1..你的TenancyOCID
region=ap-tokyo-1
key_file=C:\Users\你的名字\.oci\oci_api_key.pem
```

- [ ] **Step 4: 验证 config 能正常读取**

在 `E:\oci-vm-creator\` 目录运行：

```
python -c "import oci; c = oci.config.from_file(); print('Config OK, region:', c['region'])"
```

预期输出：`Config OK, region: ap-tokyo-1`

如果报 `FileNotFoundError` 检查 `key_file` 路径；报 `InvalidConfig` 检查各字段是否有空格或遗漏。

---

### Task 5: 运行测试和提交

- [ ] **Step 1: 启动脚本，验证重试逻辑正常**

双击 `启动.bat` 或在终端运行：

```
cd E:\oci-vm-creator
python create_vm.py
```

预期输出（容量不足时）：
```
[2026-05-19 14:32:01] OCI VM 自动重试脚本已启动（Ctrl+C 可随时停止）
[2026-05-19 14:32:01] 目标：fortune-purple-bot | Shape: VM.Standard.A1.Flex | 1 OCPU / 6 GB
[2026-05-19 14:32:01] ------------------------------------------------------------
[2026-05-19 14:32:01] 第 1 次尝试...
[2026-05-19 14:32:03] 容量不足，60 秒后重试
[2026-05-19 14:33:03] 第 2 次尝试...
```

- [ ] **Step 2: 测试 Ctrl+C 干净退出**

脚本运行中按 Ctrl+C，预期输出：

```
[2026-05-19 14:33:05] 已手动停止，共尝试 2 次。
```

终端返回到命令提示符，无异常堆栈。

- [ ] **Step 3: 提交脚本文件到 git（可选，因为是独立文件夹不在 Bot 仓库）**

如果想版本管理，在 `E:\oci-vm-creator\` 初始化 git：

```bash
cd E:\oci-vm-creator
git init
git add create_vm.py requirements.txt 启动.bat
git commit -m "feat: OCI VM auto-retry script"
```

---

## 成功的样子

VM 抢到时，终端显示：

```
[2026-05-19 18:45:23] 第 47 次尝试...
[2026-05-19 18:45:25] 请求已提交，实例 ID: ocid1.instance.oc1...
[2026-05-19 18:45:25] 轮询实例状态，等待 RUNNING...
[2026-05-19 18:45:35] 当前状态: PROVISIONING，10 秒后再查...
[2026-05-19 18:46:05] 当前状态: STARTING，10 秒后再查...
[2026-05-19 18:46:15] 成功！公网 IP: 140.83.xx.xx
```

同时弹出 Windows Toast 通知。
