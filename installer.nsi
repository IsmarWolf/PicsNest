# Installer settings
!define APPNAME "PicsNest"
!define COMPANYNAME "IsmarWolf"
!define DESCRIPTION "Image and Video Management Application"
!define VERSIONMAJOR 1
!define VERSIONMINOR 0
!define VERSIONBUILD 0

# Required plugins
!include "MUI2.nsh"
!include "FileFunc.nsh"

# Define installer name
Name "${APPNAME}"
OutFile "PicsNest_Setup.exe"
InstallDir "$PROGRAMFILES\${COMPANYNAME}\${APPNAME}"
InstallDirRegKey HKCU "Software\${COMPANYNAME}\${APPNAME}" ""

# Set compression
SetCompressor /SOLID lzma

# Modern UI settings
!define MUI_ABORTWARNING
!define MUI_ICON "assets\picsnest_logo.ico"
!define MUI_UNICON "assets\picsnest_logo.ico"

# Define UI pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

# Set UI language
!insertmacro MUI_LANGUAGE "English"

# Installer sections
Section "Install"
    SetOutPath "$INSTDIR"
    
    # Add files
    File "dist\PicsNest.exe"
    File "LICENSE"
    File "README.md"
    File "assets\picsnest_logo.ico"
    
    # Create start menu shortcut
    CreateDirectory "$SMPROGRAMS\${COMPANYNAME}"
    CreateShortCut "$SMPROGRAMS\${COMPANYNAME}\${APPNAME}.lnk" "$INSTDIR\PicsNest.exe" "" "$INSTDIR\picsnest_logo.ico"
    
    # Create uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"
    
    # Store installation folder
    WriteRegStr HKCU "Software\${COMPANYNAME}\${APPNAME}" "" $INSTDIR
    
    # Add uninstall information to Add/Remove Programs
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "DisplayName" "${APPNAME}"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "UninstallString" "$\"$INSTDIR\Uninstall.exe$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "QuietUninstallString" "$\"$INSTDIR\Uninstall.exe$\" /S"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "DisplayIcon" "$\"$INSTDIR\picsnest_logo.ico$\""
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "Publisher" "${COMPANYNAME}"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}" "NoRepair" 1
SectionEnd

# Uninstaller section
Section "Uninstall"
    # Remove installed files
    Delete "$INSTDIR\PicsNest.exe"
    Delete "$INSTDIR\LICENSE"
    Delete "$INSTDIR\README.md"
    Delete "$INSTDIR\assets\picsnest_logo.ico"
    Delete "$INSTDIR\Uninstall.exe"
    
    # Remove start menu shortcut
    Delete "$SMPROGRAMS\${COMPANYNAME}\${APPNAME}.lnk"
    RMDir "$SMPROGRAMS\${COMPANYNAME}"
    
    # Remove installation directory
    RMDir "$INSTDIR"
    
    # Remove registry entries
    DeleteRegKey HKCU "Software\${COMPANYNAME}\${APPNAME}"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${COMPANYNAME}_${APPNAME}"
SectionEnd
