# 把 ExportShipStatus 做成 Aslain 可导入的 mod

本文回答两件事：

1. Aslain 的《战舰世界》工具支持什么样的自定义 mod；
2. ExportShipStatus 应该打成什么结构，才能被它们自动安装。

结论先行：**Aslain 有两套产品，自定义 mod 的放置目录不同，但最终都落到
`<game>\bin\<当前 build>\res_mods\`。** 用下面这个不带版本目录的结构，可以同时兼容两套：

```text
ExportShipStatus-aslain.zip
└─ res_mods/
   ├─ PnFModsLoader.py                  （0 字节，加载开关）
   └─ PnFMods/
      └─ ExportShipStatus/
         ├─ Main.py
         └─ core.py
```

仓库根目录的 `ExportShipStatus-aslain.zip` 就是按这个结构生成的；改动源码后运行
`package-aslain.bat` 重新生成。

---

## 1. Aslain 的两套产品

| | 经典安装器（Classic Modpack） | 新版 Mod Manager |
|---|---|---|
| 程序 | `Aslains_WoWs_Modpack_Installer_v.*.exe` | `Aslain's WoWs Mod Manager` |
| 自定义 mod 目录 | `<game>\Aslain_Modpack\Custom_mods\` | `<game>\Aslain_custom_mods\` |
| 压缩包格式 | `.zip`、`.7z` | `.zip`、`.7z`、`.rar` |
| 压缩包内路径 | **必须**以 `res_mods\` 开头，**不要**版本号目录 | 推荐 `res_mods\version\...`；也接受 `res_mods\...` |
| 直接放文件夹 | 支持，只处理 `Custom_mods\res_mods\` | 支持，处理 `Aslain_custom_mods\res_mods\version\` |
| 应用时机 | 主安装结束后 | 目录 mod 安装结束后（会覆盖目录 mod 的同名文件） |
| 目标位置 | `bin\<当前 build>\res_mods\...` | `bin\<当前 build>\res_mods\...` |

两套产品的“自定义 mod”功能本质上都是**按游戏目录结构解压文件**，不是带清单的插件系统。
因此 ExportShipStatus 不需要 `manifest.xml`，也不需要额外的元数据文件。

### 1.1 经典安装器

Aslain 15.10.0 安装器生成的
`<game>\Aslain_Modpack\Custom_mods\README.txt` 写得很明确：

- 把 `.zip` 或 `.7z` 放在 `Custom_mods` 或其子文件夹；
- 压缩包内是“要解压的游戏文件夹结构”，例如：
  `res_mods\gui\flash\application.swf`；
- 也可以直接把文件放到 `Custom_mods\res_mods\`，会复制到
  `<game>\bin\<game bin>\res_mods\...`；
- 直接文件夹模式只处理 `res_mods`，其他文件夹忽略；
- 已有文件会被覆盖；
- 顺序：先复制直接的 `res_mods`，最后解压压缩包。

安装器日志里能看到实际落点（一次 15.8 安装）：

```text
[CustomMods] Processing ...\Aslain_Modpack\Custom_mods -> ...\World of Warships\bin\13187581
[CustomMods] Done
```

> 旧版安装器/论坛帖里这个目录也可能叫 `Aslains_Custom_mods`。以你当前安装器
> 生成的目录和其中的 `README.txt` 为准；15.10.0 的经典安装器实际使用的是
> `Aslain_Modpack\Custom_mods`。

Aslain 在 2025-07-05 的论坛回复中还特别纠正过一个常见错误：**WoWs 的 zip 里不要放
版本号文件夹**，应该用 `res_mods/gui/...`，而不是 `res_mods/<version>/...`。

### 1.2 新版 Mod Manager

新版应用在游戏根目录生成 `Aslain_custom_mods`，同目录的 `README.txt` 规则是：

- `.zip`、`.7z`、`.rar` 均可，放在该目录或其子文件夹；
- 压缩包内推荐：
  `res_mods\version\gui\flash\application.swf`
  （`version` 是占位符）；
- 直接文件夹：`Aslain_custom_mods\res_mods\version\...`；
- 顺序：先处理直接的 `res_mods`，再解压压缩包；
- 已有文件覆盖；
- 删除 `Aslain_custom_mods` 里的源文件后，下一次 Apply 会把已安装的副本移除。

应用界面里也可以通过 **Settings → Custom mods → Add mods...** 导入；
它会把压缩包复制进 `Aslain_custom_mods`，只接受 `.zip`、`.7z`、`.rar`，
并提示“a mod must be a .zip, .7z or .rar archive that holds its res_mods\ folder”。

#### `res_mods\version\` 在 WoWs 里到底映射到哪里

新版应用反编译后的路径逻辑（`InstallService.RemapEntryPath` / `Brand.ResModsRoot`）是：

- `Brand.VersionIsBinFolder = true`；
- `ResModsRoot(version) = bin\<version>\res_mods`，这里的 `version` 是**当前激活的
  `bin` 目录名**（例如 `13533378`），不是显示版本 `15.10.0`；
- 对 `res_mods/<version|数字版本>/...`：跳过该版本段，映射到
  `bin\<当前 build>\res_mods\...`；
- 对 `res_mods/...`：直接映射到 `bin\<当前 build>\res_mods\...`。

所以对 WoWs 来说：

```text
res_mods\version\PnFMods\ExportShipStatus\Main.py
res_mods\15.10.0\PnFMods\ExportShipStatus\Main.py
res_mods\PnFMods\ExportShipStatus\Main.py
```

三者最终都会落到：

```text
bin\<当前 build>\res_mods\PnFMods\ExportShipStatus\Main.py
```

`version` 占位符不是必需的；但用上它更符合新版 README 的描述，也方便同一个包在
不同显示版本之间复用。**为了同时兼容经典安装器，本仓库的包采用不带版本目录的写法。**

---

## 2. 为什么这个包能同时兼容两套

- 经典安装器要求压缩包根下直接是 `res_mods\...`，不能中间夹版本号；
- 新版 Mod Manager 的 `RemapEntryPath` 对 `res_mods\PnFMods\...` 同样接受；
- 于是下面这个“最小公共结构”同时成立：

```text
res_mods\PnFModsLoader.py
res_mods\PnFMods\ExportShipStatus\Main.py
res_mods\PnFMods\ExportShipStatus\core.py
```

如果只面向新版 Manager，也可以把整个 `res_mods` 换成
`res_mods\version`，效果相同；但那样放进经典安装器会多出一层 `version` 目录，
所以不推荐作为通用包。

### 关于 `PnFModsLoader.py`

`PnFModsLoader.py` 是 PnFMods 的**加载开关**：文件存在即可，内容可以是 0 字节。
Aslain 目录里的 PnF mod 包（例如 TTaro Minimap、Consumables Monitor）也都会带一个
0 字节的同名文件。因此包里带上它是安全的，尤其是在“只装了这个自定义 mod、没有选任何
PnF 目录 mod”的情况下，能保证游戏会扫描 `PnFMods\`。

> 如果你机器上的 `res_mods\PnFModsLoader.py` 是某个第三方提供的**非空**加载器，
> 不要用本包的 0 字节文件覆盖它：把 zip 里的 `res_mods/PnFModsLoader.py` 删掉，
> 依赖已有的加载器即可。

---

## 3. 生成导入包

```bat
package-aslain.bat
```

生成：

```text
ExportShipStatus-aslain.zip
```

脚本只复制 `src\ExportShipStatus\Main.py` 和 `core.py`，不会把 `__pycache__` 带进去；
`PnFModsLoader.py` 用 `type nul` 生成 0 字节文件。压缩由
`tools\make-aslain-zip.ps1` 完成，ZIP 内部统一使用 `/` 作为分隔符
（PowerShell 5.1 的 `Compress-Archive` 会写反斜杠，部分解压器会把它当成文件名的一部分）。

**打包要点：**

- `res_mods` 必须在压缩包**根**，不要出现 `ExportShipStatus\res_mods\...` 这种多一层；
- 不要放 `res_mods\15.10.0\...`（对经典安装器是错的）；
- 不要把接收端、VTS/OBS 桥、开发文档等非游戏侧文件打进去；
- `.py` 源码可以直接被 PnFMods 加载，不需要编译成 `.pyc`。

---

## 4. 安装

### 4.1 新版 Aslain's WoWs Mod Manager

1. 关闭游戏客户端（应用在 Apply 时不应有游戏进程占用 `res_mods`）。
2. 把 `ExportShipStatus-aslain.zip` 放进：

   ```text
   <game>\Aslain_custom_mods\
   ```

   或在应用里 **Settings → Custom mods → Add mods...** 选择这个 zip。
3. 在应用里选好其他目录 mod，点击 **Install / Apply**。
4. 应用会在目录 mod 之后处理自定义 mod，把它们解压到：

   ```text
   <game>\bin\<当前 build>\res_mods\PnFMods\ExportShipStatus\
   ```

5. 启动游戏，进入一场战斗验证（见第 5 节）。

游戏更新后，Manager 会在下一次 Apply 时自动把自定义 mod 重新应用到新的 `bin\<build>`；
如果源 zip 还在 `Aslain_custom_mods` 里，不需要手动重装。

### 4.2 经典 Aslain 安装器

1. 关闭游戏客户端。
2. 把 `ExportShipStatus-aslain.zip` 放进：

   ```text
   <game>\Aslain_Modpack\Custom_mods\
   ```

3. 正常运行 Aslain 安装器，选择你常用的 mod，完成安装。
4. 安装器最后会执行 `[CustomMods]`，把 zip 解压到当前 `bin\<build>\res_mods\`。
5. 启动游戏验证。

游戏大更新会新建 `bin\<新 build>`；经典安装器不会自动后台运行，**更新后需要重新运行一次
安装器**（自定义 mod 会再次被应用）。

---

## 5. 验证清单

安装后检查文件：

```text
<game>\bin\<build>\res_mods\PnFModsLoader.py       存在（通常 0 字节）
<game>\bin\<build>\res_mods\PnFMods\ExportShipStatus\Main.py
<game>\bin\<build>\res_mods\PnFMods\ExportShipStatus\core.py
```

启动游戏后检查日志：

```text
<game>\profile\python.log
```

应出现类似：

```text
[ExportShipStatus] Created instance, waiting for battle
```

进入战斗后：

```text
<game>\profile\wows_telemetry.jsonl
```

应开始追加 `battle_start`、`snapshot` 等 JSON Lines；另开终端运行配套仓库的接收端
（`receiver/receiver.py`）应能持续打印快照。

### 没生效时先查这三处

1. **build 目录对不对**：`bin` 下可能有多个版本目录，游戏实际运行的是最新的/当前激活的
   那个；预下载可能创建一个尚不能用的新目录。以 `bin` 下实际运行版本为准。
2. **loader 在不在**：`python.log` 里若有
   `'PnFModsLoader.py' was not found at './res_mods/'`，说明加载开关缺失。
3. **看安装器日志**：
   - Manager：`C:\ProgramData\Aslain\WoWsModManager\Aslain.WoWsModManager.log`
   - 经典安装器：`<game>\Aslain_Modpack\Logs\Aslains_Installer.log`
     搜索 `[CustomMods]` 和 `CUSTOM`。

---

## 6. 关于 ModForge 和 `manifest.xml`

Aslain 新版目录里的 UI mod 使用 TTaro 的 **ModForge**（`res_mods\ForgeBlueprints\` +
`PnFMods\*\manifest.xml`）。那是 ModForge 用来合并 Unbound 1 XML 蓝图的机制，
**不是 Aslain 自定义 mod 的导入格式**。

ExportShipStatus 是 PnFMods 的 Python mod（`Main.py` + `core.py`），不修改游戏 UI XML，
因此：

- 不需要 `manifest.xml`；
- 不需要 `ForgeBlueprints`；
- 只要按游戏目录结构放到 `res_mods\PnFMods\ExportShipStatus\` 即可。

---

## 7. 版本与合规提醒

- 本包解决的是**导入格式**问题；运行兼容性仍取决于游戏版本和 Mods API。
  项目在 15.8.0 真机验证过；本文的导入路径映射在 15.10.0 环境核对过，导入后请在训练房确认
  `python.log` 和 `wows_telemetry.jsonl` 是否正常。
- Aslain 目录中的 mod 经过 WG 审核；自定义 mod 不在审核范围内。ExportShipStatus
  仅读取本船可见信息、无自动化、不修改游戏文件，按项目 README 的合规定位自用。
- 不要把 `profile\wows_telemetry.jsonl` 或接收端一起打进 Aslain 包；它们不属于游戏侧文件。

---

## 8. 参考资料

- Aslain's WoWs Modpack 下载页（含经典安装器与 Mod Manager 下载）：
  <https://aslain.com/index.php?/topic/2020-download-%E2%98%85-world-of-warships-%E2%98%85-modpack/>
- Aslain 论坛“custom mod issues”帖（WoWs 不要版本号目录的官方回复）：
  <https://aslain.com/index.php?/topic/34437-custom-mod-issues/>
- Aslain 论坛 Aslains_Custom_mods 说明（WoT 版；WoWs 的差异以 34437 与安装器生成的 README 为准）：
  <https://aslain.com/index.php?/topic/26621-aslains_custom_mods/>
- Aslain Mod Manager 讨论帖：
  <https://aslain.com/index.php?/topic/36121-aslain-mod-manager/>
- TTaro ModForge（新版 UI mod 的蓝图安装器，非自定义 mod 格式）：
  <https://github.com/AndrewTaro/ModForge>
- WG Mods API 文档（PnFMods 的 `Main.py` / API 版本）：
  <https://github.com/wgmods/Mods-API-Documentation>
- Aslain 15.10.0 安装器生成的 `Aslain_Modpack\Custom_mods\README.txt`
  与 Mod Manager 生成的 `Aslain_custom_mods\README.txt`（路径规则的第一手依据）。
