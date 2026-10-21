; QQ Bot生成器 安装包（NSIS 3 / Unicode）
; 编译：makensis installer\qqbot-generator.nsi
; 产物：dist\QQ Bot生成器-安装包.exe

Unicode true
!include "MUI2.nsh"
!include "FileFunc.nsh"

!define APP_NAME "QQ Bot生成器"
!define APP_VERSION "3.8.2"
!define APP_EXE "QQ Bot生成器.exe"
!define APP_PUBLISHER "QQ Bot Generator"
!define APP_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\QQBotGenerator"

Name "${APP_NAME}"
OutFile "..\dist\${APP_NAME}-安装包.exe"
InstallDir "$LOCALAPPDATA\Programs\QQBotGenerator"
InstallDirRegKey HKCU "Software\QQBotGenerator" "InstallDir"
RequestExecutionLevel user
SetCompressor /SOLID lzma
SetCompressorDictSize 32
BrandingText "${APP_NAME} v${APP_VERSION}"

VIProductVersion "3.8.2.0"
VIAddVersionKey "ProductName" "${APP_NAME}"
VIAddVersionKey "FileDescription" "${APP_NAME} 安装程序"
VIAddVersionKey "FileVersion" "${APP_VERSION}"
VIAddVersionKey "ProductVersion" "${APP_VERSION}"
VIAddVersionKey "LegalCopyright" "MIT License"
VIAddVersionKey "CompanyName" "${APP_PUBLISHER}"

!define MUI_ABORTWARNING
!define MUI_ICON "..\assets\icon.ico"
!define MUI_UNICON "..\assets\icon.ico"
!define MUI_WELCOMEPAGE_TITLE "安装 ${APP_NAME}"
!define MUI_WELCOMEPAGE_TEXT "把一条会聊天的胖鱼装进你的电脑。$\r$\n$\r$\n装好后：填模型 Key → 启动 NapCat 扫码 → 回首页启动机器人。$\r$\n$\r$\n程序按用户安装，不需要管理员权限；聊天数据会保存在你的用户目录里。"
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "立即打开 ${APP_NAME}"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "SimpChinese"

LangString DESC_SEC_MAIN ${LANG_SIMPCHINESE} "主程序与卸载器（必装）"
LangString DESC_SEC_DESKTOP ${LANG_SIMPCHINESE} "在桌面放一个快捷方式"

Section "主程序" SEC_MAIN
    SectionIn RO
    SetOutPath "$INSTDIR"
    File "..\dist\${APP_EXE}"

    WriteUninstaller "$INSTDIR\uninstall.exe"
    CreateDirectory "$SMPROGRAMS\${APP_NAME}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
    CreateShortCut "$SMPROGRAMS\${APP_NAME}\卸载 ${APP_NAME}.lnk" "$INSTDIR\uninstall.exe"

    WriteRegStr HKCU "Software\QQBotGenerator" "InstallDir" "$INSTDIR"
    WriteRegStr HKCU "${APP_KEY}" "InstallLocation" "$INSTDIR"
    WriteRegStr HKCU "${APP_KEY}" "DisplayName" "${APP_NAME}"
    WriteRegStr HKCU "${APP_KEY}" "DisplayVersion" "${APP_VERSION}"
    WriteRegStr HKCU "${APP_KEY}" "Publisher" "${APP_PUBLISHER}"
    WriteRegStr HKCU "${APP_KEY}" "DisplayIcon" "$INSTDIR\${APP_EXE}"
    WriteRegStr HKCU "${APP_KEY}" "UninstallString" '"$INSTDIR\uninstall.exe"'
    WriteRegStr HKCU "${APP_KEY}" "QuietUninstallString" '"$INSTDIR\uninstall.exe" /S'
    WriteRegDWORD HKCU "${APP_KEY}" "NoModify" 1
    WriteRegDWORD HKCU "${APP_KEY}" "NoRepair" 1

    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKCU "${APP_KEY}" "EstimatedSize" "$0"
SectionEnd

Section /o "桌面快捷方式" SEC_DESKTOP
    CreateShortCut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}"
SectionEnd

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
!insertmacro MUI_DESCRIPTION_TEXT ${SEC_MAIN} $(DESC_SEC_MAIN)
!insertmacro MUI_DESCRIPTION_TEXT ${SEC_DESKTOP} $(DESC_SEC_DESKTOP)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
    Delete "$INSTDIR\${APP_EXE}"
    Delete "$INSTDIR\uninstall.exe"
    RMDir "$INSTDIR"

    Delete "$DESKTOP\${APP_NAME}.lnk"
    RMDir /r "$SMPROGRAMS\${APP_NAME}"

    DeleteRegKey HKCU "${APP_KEY}"
    DeleteRegKey HKCU "Software\QQBotGenerator"
SectionEnd
