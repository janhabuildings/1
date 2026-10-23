"""Generate a real dependency-free Xcode project using checked-in Swift sources."""
from pathlib import Path
import hashlib

ROOT=Path(__file__).resolve().parents[1]/'ios'
project=ROOT/'JBIInspections.xcodeproj';project.mkdir(exist_ok=True)

def identity(name): return hashlib.sha1(name.encode()).hexdigest()[:24].upper()
def q(value): return '"'+value.replace('\\','\\\\').replace('"','\\"')+'"'
objects=[]
def obj(key,body): objects.append(f'{identity(key)} = {{ {body} }};')
sources=sorted((ROOT/'JBIInspections').glob('*.swift'))
for path in sources:
    obj('file-'+path.name,f'isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = {q(path.name)}; sourceTree = "<group>";')
    obj('build-'+path.name,f'isa = PBXBuildFile; fileRef = {identity("file-"+path.name)};')
obj('plist','isa = PBXFileReference; lastKnownFileType = text.plist.xml; path = Info.plist; sourceTree = "<group>";')
obj('privacy','isa = PBXFileReference; lastKnownFileType = text.xml; path = PrivacyInfo.xcprivacy; sourceTree = "<group>";')
obj('privacybuild',f'isa = PBXBuildFile; fileRef = {identity("privacy")};')
obj('assets','isa = PBXFileReference; lastKnownFileType = folder.assetcatalog; path = Assets.xcassets; sourceTree = "<group>";')
obj('assetsbuild',f'isa = PBXBuildFile; fileRef = {identity("assets")};')
obj('product','isa = PBXFileReference; explicitFileType = wrapper.application; includeInIndex = 0; path = JBIInspections.app; sourceTree = BUILT_PRODUCTS_DIR;')
obj('sourcegroup','isa = PBXGroup; children = ('+','.join(identity('file-'+p.name) for p in sources)+','+identity('plist')+','+identity('privacy')+','+identity('assets')+'); path = JBIInspections; sourceTree = "<group>";')
obj('products',f'isa = PBXGroup; children = ({identity("product")}); name = Products; sourceTree = "<group>";')
obj('main',f'isa = PBXGroup; children = ({identity("sourcegroup")},{identity("products")}); sourceTree = "<group>";')
obj('sources','isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ('+','.join(identity('build-'+p.name) for p in sources)+'); runOnlyForDeploymentPostprocessing = 0;')
for phase,isa in [('frameworks','PBXFrameworksBuildPhase'),('resources','PBXResourcesBuildPhase')]:
    files=identity('privacybuild')+','+identity('assetsbuild') if phase=='resources' else ''
    obj(phase,f'isa = {isa}; buildActionMask = 2147483647; files = ({files}); runOnlyForDeploymentPostprocessing = 0;')
for config in ['Debug','Release']:
    project_settings={'CLANG_ENABLE_MODULES':'YES','SWIFT_VERSION':'5.0','IPHONEOS_DEPLOYMENT_TARGET':'17.0',
                      'SDKROOT':'iphoneos','ENABLE_USER_SCRIPT_SANDBOXING':'YES',
                      'DEBUG_INFORMATION_FORMAT':'dwarf' if config=='Debug' else 'dwarf-with-dsym',
                      'SWIFT_OPTIMIZATION_LEVEL':'-Onone' if config=='Debug' else '-O',
                      'SWIFT_ACTIVE_COMPILATION_CONDITIONS':'DEBUG' if config=='Debug' else ''}
    target_settings={'PRODUCT_BUNDLE_IDENTIFIER':'nyc.dseny.JBIInspections','PRODUCT_NAME':'$(TARGET_NAME)',
                     'INFOPLIST_FILE':'JBIInspections/Info.plist','GENERATE_INFOPLIST_FILE':'NO',
                     'ASSETCATALOG_COMPILER_APPICON_NAME':'AppIcon','CODE_SIGN_STYLE':'Automatic','TARGETED_DEVICE_FAMILY':'1',
                     'CURRENT_PROJECT_VERSION':'1','MARKETING_VERSION':'0.1.0','ENABLE_PREVIEWS':'YES',
                     'LD_RUNPATH_SEARCH_PATHS':'$(inherited) @executable_path/Frameworks'}
    for scope,values in [('project',project_settings),('target',target_settings)]:
        obj(scope+config,'isa = XCBuildConfiguration; buildSettings = {'+''.join(k+' = '+q(v)+';' for k,v in values.items())+'}; name = '+config+';')
for scope in ['project','target']:
    obj(scope+'configs',f'isa = XCConfigurationList; buildConfigurations = ({identity(scope+"Debug")},{identity(scope+"Release")}); defaultConfigurationIsVisible = 0; defaultConfigurationName = Release;')
obj('target',f'isa = PBXNativeTarget; buildConfigurationList = {identity("targetconfigs")}; buildPhases = ({identity("sources")},{identity("frameworks")},{identity("resources")}); buildRules = (); dependencies = (); name = JBIInspections; productName = JBIInspections; productReference = {identity("product")}; productType = "com.apple.product-type.application";')
obj('project',f'isa = PBXProject; attributes = {{ LastUpgradeCheck = 1600; TargetAttributes = {{ {identity("target")} = {{ CreatedOnToolsVersion = 16.0; }}; }}; }}; buildConfigurationList = {identity("projectconfigs")}; compatibilityVersion = "Xcode 14.0"; developmentRegion = en; hasScannedForEncodings = 0; knownRegions = (en,Base); mainGroup = {identity("main")}; productRefGroup = {identity("products")}; projectDirPath = ""; projectRoot = ""; targets = ({identity("target")});')
(project/'project.pbxproj').write_text('// !$*UTF8*$!\n{ archiveVersion = 1; classes = {}; objectVersion = 56; objects = {\n'+'\n'.join(objects)+'\n}; rootObject = '+identity('project')+'; }\n')
schemes=project/'xcshareddata/xcschemes';schemes.mkdir(parents=True,exist_ok=True)
ref=f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{identity("target")}" BuildableName="JBIInspections.app" BlueprintName="JBIInspections" ReferencedContainer="container:JBIInspections.xcodeproj"/>'
(schemes/'JBIInspections.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="1600" version="1.3">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries><BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{ref}</BuildActionEntry></BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"/>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" debugServiceExtension="internal" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{ref}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>''')
print(project)
