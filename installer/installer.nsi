;AI自动写小说系统 - NSIS安装程序脚本
;用法: makensis installer.nsi

!include "MUI2.nsh"
!include "FileFunc.nsh"

;--------------------------------
; 基本配置
;--------------------------------

Name "AI自动写小说系统"
OutFile "AI_NovelWriter_Setup.exe"
InstallDir "$PROGRAMFILES\AI_NovelWriter"
InstallDirRegKey HKLM "Software\AI_NovelWriter" "InstallDir"
RequestExecutionLevel admin

; 版本信息
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "AI自动写小说系统"
VIAddVersionKey "CompanyName" "AI Novel Writer"
VIAddVersionKey "FileVersion" "1.0.0"
VIAddVersionKey "FileDescription" "AI自动写小说系统安装程序"
VIAddVersionKey "LegalCopyright" "© 2026 AI Novel Writer"

;--------------------------------
; 界面配置
;--------------------------------

!define MUI_ABORTWARNING
!define MUI_ICON "..\icon.ico"
!define MUI_UNICON "..\icon.ico"

; 欢迎页面
!define MUI_WELCOMEPAGE_TITLE "欢迎安装 AI自动写小说系统"
!define MUI_WELCOMEPAGE_TEXT "AI自动写小说系统是一个完整的AI小说生成产品，支持多种小说类型、本地模型和云端API集成。$\r$\n$\r$\n功能特性：$\r$\n  - 多类型小说生成（科幻、悬疑、言情、奇幻、都市）$\r$\n  - 智能生成引擎（大纲、章节、人物生成）$\r$\n  - 向量检索增强（确保剧情连贯性）$\r$\n  - 一致性审校（检测逻辑冲突）$\r$\n  - 情景对话推演$\r$\n  - 故事流推演$\r$\n  - 风格转换$\r$\n  - 事物描写库$\r$\n  - 角色桥段库$\r$\n$\r$\n点击'下一步'继续安装。"

; 许可协议页面
!define MUI_LICENSEPAGE_TEXT_TOP "请仔细阅读以下许可协议："
!define MUI_LICENSEPAGE_TEXT_BOTTOM "如果您接受协议中的条款，请点击'我接受'继续安装。"
!define MUI_LICENSEPAGE_BUTTON "我接受(&I)"

; 安装目录选择页面
!define MUI_DIRECTORYPAGE_TEXT_TOP "请选择安装目录："

; 安装完成页面
!define MUI_FINISHPAGE_RUN "$INSTDIR\AI_NovelWriter.exe"
!define MUI_FINISHPAGE_RUN_TEXT "启动 AI自动写小说系统"
!define MUI_FINISHPAGE_LINK "访问项目主页"
!define MUI_FINISHPAGE_LINK_LOCATION "https://github.com/your-repo/ai-novel-writer"

;--------------------------------
; 页面定义
;--------------------------------

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "license.txt"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; 语言文件
;--------------------------------

!insertmacro MUI_LANGUAGE "SimpChinese"

;--------------------------------
; 安装类型
;--------------------------------

InstType "完整安装"
InstType "最小安装"

;--------------------------------
; 安装部分
;--------------------------------

Section "核心文件" SecCore
    SectionIn 1 2
    
    ; 设置输出路径
    SetOutPath "$INSTDIR"
    
    ; 安装主程序
    File "dist\AI_NovelWriter.exe"
    
    ; 安装服务程序
    File "dist\AI_NovelService.exe"
    File "dist\NovelGenerator.exe"
    
    ; 安装配置文件
    File "config.json"
    File "license.txt"
    
    ; 创建目录
    CreateDirectory "$INSTDIR\bin"
    CreateDirectory "$INSTDIR\config"
    CreateDirectory "$INSTDIR\data"
    CreateDirectory "$INSTDIR\logs"
    CreateDirectory "$INSTDIR\models"
    CreateDirectory "$INSTDIR\models\local"
    
    ; 写入注册表
    WriteRegStr HKLM "Software\AI_NovelWriter" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\AI_NovelWriter" "Version" "1.0.0"
    
    ; 创建卸载程序
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    ; 添加到程序列表
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "DisplayName" "AI自动写小说系统"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "UninstallString" "$\"$INSTDIR\uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "DisplayIcon" "$\"$INSTDIR\AI_NovelWriter.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "Publisher" "AI Novel Writer"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "DisplayVersion" "1.0.0"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "NoRepair" 1
    
    ; 获取安装大小
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter" \
        "EstimatedSize" "$0"
SectionEnd

Section "前端资源" SecFrontend
    SectionIn 1
    
    SetOutPath "$INSTDIR\frontend"
    
    ; 安装前端文件
    File /r "frontend\public\*.*"
SectionEnd

Section "文档" SecDocs
    SectionIn 1
    
    SetOutPath "$INSTDIR\docs"
    
    ; 安装文档文件
    File /r "docs\*.*"
    File "README_CN.md"
    File "NEW_FEATURES.md"
    File "QUICKSTART.md"
    File "USAGE.md"
SectionEnd

Section "示例模型" SecModels
    SectionIn 1
    
    SetOutPath "$INSTDIR\models"
    
    ; 创建示例模型配置
    FileOpen $0 "$INSTDIR\models\example.txt" w
    FileWrite $0 "将您的模型文件放在此目录下$\r$\n"
    FileWrite $0 "支持的格式：.gguf, .ggml, .bin, .pt, .pth$\r$\n"
    FileWrite $0 "$\r$\n"
    FileWrite $0 "推荐模型：$\r$\n"
    FileWrite $0 "  - Qwen3.6 (推荐)$\r$\n"
    FileWrite $0 "  - Llama3$\r$\n"
    FileWrite $0 "  - ChatGLM$\r$\n"
    FileClose $0
SectionEnd

Section "桌面快捷方式" SecDesktop
    SectionIn 1
    
    CreateShortcut "$DESKTOP\AI自动写小说系统.lnk" "$INSTDIR\AI_NovelWriter.exe" "" "$INSTDIR\AI_NovelWriter.exe" 0
SectionEnd

Section "开始菜单" SecStartMenu
    SectionIn 1
    
    CreateDirectory "$SMPROGRAMS\AI自动写小说系统"
    CreateShortcut "$SMPROGRAMS\AI自动写小说系统\AI自动写小说系统.lnk" "$INSTDIR\AI_NovelWriter.exe" "" "$INSTDIR\AI_NovelWriter.exe" 0
    CreateShortcut "$SMPROGRAMS\AI自动写小说系统\卸载.lnk" "$INSTDIR\uninstall.exe" "" "$INSTDIR\uninstall.exe" 0
    CreateShortcut "$SMPROGRAMS\AI自动写小说系统\文档.lnk" "$INSTDIR\docs" "" "" 0
SectionEnd

;--------------------------------
; 安装前检查
;--------------------------------

Function .onInit
    ; 检查是否已安装
    ReadRegStr $0 HKLM "Software\AI_NovelWriter" "InstallDir"
    StrCmp $0 "" done
    
    MessageBox MB_YESNO|MB_ICONQUESTION "检测到已安装 AI自动写小说系统。$\r$\n$\r$\n是否要覆盖安装？$\r$\n$\r$\n注意：覆盖安装将保留您的配置和数据。" IDYES done
    Abort
    
    done:
FunctionEnd

;--------------------------------
; 安装后操作
;--------------------------------

Function .onInstSuccess
    ; 创建配置文件（如果不存在）
    IfFileExists "$INSTDIR\config.json" config_exists
    FileOpen $0 "$INSTDIR\config.json" w
    FileWrite $0 '{$\r$\n'
    FileWrite $0 '  "ai_service_port": 8001,$\r$\n'
    FileWrite $0 '  "novel_service_port": 8002,$\r$\n'
    FileWrite $0 '  "frontend_port": 3000,$\r$\n'
    FileWrite $0 '  "auto_open_browser": true$\r$\n'
    FileWrite $0 '}$\r$\n'
    FileClose $0
    
    config_exists:
FunctionEnd

;--------------------------------
; 卸载部分
;--------------------------------

Section "Uninstall"
    ; 停止服务（如果正在运行）
    ExecWait 'taskkill /F /IM AI_NovelService.exe' $0
    ExecWait 'taskkill /F /IM NovelGenerator.exe' $0
    
    ; 删除文件
    Delete "$INSTDIR\AI_NovelWriter.exe"
    Delete "$INSTDIR\AI_NovelService.exe"
    Delete "$INSTDIR\NovelGenerator.exe"
    Delete "$INSTDIR\config.json"
    Delete "$INSTDIR\license.txt"
    Delete "$INSTDIR\uninstall.exe"
    
    ; 删除目录
    RMDir /r "$INSTDIR\bin"
    RMDir /r "$INSTDIR\frontend"
    RMDir /r "$INSTDIR\docs"
    RMDir /r "$INSTDIR\logs"
    
    ; 保留用户数据
    MessageBox MB_YESNO|MB_ICONQUESTION "是否删除用户数据？$\r$\n$\r$\n包括：$\r$\n  - 配置文件$\r$\n  - 模型文件$\r$\n  - 生成的小说$\r$\n$\r$\n选择'否'将保留这些数据。" IDYES delete_data IDNO keep_data
    
    delete_data:
    RMDir /r "$INSTDIR\config"
    RMDir /r "$INSTDIR\data"
    RMDir /r "$INSTDIR\models"
    RMDir "$INSTDIR"
    Goto cleanup
    
    keep_data:
    RMDir "$INSTDIR"
    
    cleanup:
    ; 删除快捷方式
    Delete "$DESKTOP\AI自动写小说系统.lnk"
    RMDir /r "$SMPROGRAMS\AI自动写小说系统"
    
    ; 删除注册表
    DeleteRegKey HKLM "Software\AI_NovelWriter"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AI_NovelWriter"
SectionEnd

;--------------------------------
; 卸载前检查
;--------------------------------

Function un.onInit
    MessageBox MB_YESNO|MB_ICONQUESTION "确定要卸载 AI自动写小说系统 吗？" IDYES noabort
    Abort
    noabort:
FunctionEnd
