$ErrorActionPreference = "Stop"

$root = "G:\AVScope"
$executable = "$root\build\qt6\bin\AVScope.exe"
$sample = "$root\samples\sample.aac"
$output = "$root\tmp\qt-ui-validation"

& "$root\scripts\build_qt.ps1"
if ($LASTEXITCODE -ne 0) { throw "Qt build validation failed" }

New-Item -ItemType Directory -Force -Path $output | Out-Null
$env:AVSCOPE_ROOT = $root
$env:AVSCOPE_PYTHON = "E:\DevelopmentEnvironment\python\python.exe"
$env:QT_QPA_PLATFORM = "windows"
$env:PATH = "E:\QT\6.9.0\mingw_64\bin;E:\QT\Tools\mingw1310_64\bin;$env:PATH"
$env:TEMP = "$root\tmp"
$env:TMP = "$root\tmp"

foreach ($theme in @("dark", "light")) {
    $screenshot = "$output\$theme.png"
    Remove-Item -LiteralPath $screenshot -Force -ErrorAction SilentlyContinue
    $env:AVSCOPE_THEME = $theme
    $env:AVSCOPE_WINDOW_WIDTH = "1560"
    $env:AVSCOPE_WINDOW_HEIGHT = "940"
    $env:AVSCOPE_SCREENSHOT = $screenshot
    $process = Start-Process -FilePath $executable -ArgumentList $sample -WindowStyle Hidden -PassThru
    if (-not $process.WaitForExit(10000)) {
        $process.Kill()
        throw "Qt $theme theme smoke test timed out"
    }
    if (-not (Test-Path -LiteralPath $screenshot)) {
        throw "Qt $theme theme screenshot was not generated"
    }
}

$compactScreenshot = "$output\compact-1120x720.png"
Remove-Item -LiteralPath $compactScreenshot -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_THEME = "dark"
$env:AVSCOPE_WINDOW_WIDTH = "1120"
$env:AVSCOPE_WINDOW_HEIGHT = "720"
$env:AVSCOPE_START_TAB = "0"
$env:AVSCOPE_SCREENSHOT = $compactScreenshot
$compactProcess = Start-Process -FilePath $executable -ArgumentList $sample -WindowStyle Hidden -PassThru
if (-not $compactProcess.WaitForExit(10000)) {
    $compactProcess.Kill()
    throw "Qt compact layout smoke test timed out"
}
if (-not (Test-Path -LiteralPath $compactScreenshot)) {
    throw "Qt compact layout screenshot was not generated"
}
Remove-Item Env:\AVSCOPE_WINDOW_WIDTH, Env:\AVSCOPE_WINDOW_HEIGHT, Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue
$env:AVSCOPE_WINDOW_WIDTH = "1560"
$env:AVSCOPE_WINDOW_HEIGHT = "940"

$timelineScreenshot = "$output\timeline-pcap.png"
Remove-Item -LiteralPath $timelineScreenshot -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_THEME = "dark"
$env:AVSCOPE_START_TAB = "3"
$env:AVSCOPE_SCREENSHOT = $timelineScreenshot
$timelineProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.pcap" -WindowStyle Hidden -PassThru
if (-not $timelineProcess.WaitForExit(10000)) {
    $timelineProcess.Kill()
    throw "Qt timeline smoke test timed out"
}
if (-not (Test-Path -LiteralPath $timelineScreenshot)) {
    throw "Qt timeline screenshot was not generated"
}
Remove-Item Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue

$rtcpPreviewScreenshot = "$output\pcap-rtcp-preview.png"
$rtcpPreviewJson = "$output\pcap-rtcp-preview.json"
Remove-Item -LiteralPath $rtcpPreviewScreenshot, $rtcpPreviewJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "4"
$env:AVSCOPE_SCREENSHOT = $rtcpPreviewScreenshot
$rtcpPreviewProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.pcap" -WindowStyle Hidden -PassThru
if (-not $rtcpPreviewProcess.WaitForExit(10000)) {
    $rtcpPreviewProcess.Kill()
    throw "Qt RTCP preview smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rtcpPreviewScreenshot)) {
    throw "Qt RTCP preview screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rtcpPreviewJson -Force
Remove-Item Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue

$transportScreenshot = "$output\transport-sessions.png"
$transportJson = "$output\transport-sessions.json"
$transportState = "$output\transport-sessions-state.json"
Remove-Item -LiteralPath $transportScreenshot, $transportJson, $transportState -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "8"
$env:AVSCOPE_TRANSPORT_ISSUES_ONLY = "1"
$env:AVSCOPE_TRANSPORT_STATE = $transportState
$env:AVSCOPE_SCREENSHOT = $transportScreenshot
$transportProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample_rtp_anomalies.pcap" -WindowStyle Hidden -PassThru
if (-not $transportProcess.WaitForExit(10000)) {
    $transportProcess.Kill()
    throw "Qt transport session smoke test timed out"
}
if (-not (Test-Path -LiteralPath $transportScreenshot)) {
    throw "Qt transport session screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $transportJson -Force
Remove-Item Env:\AVSCOPE_START_TAB, Env:\AVSCOPE_TRANSPORT_ISSUES_ONLY, Env:\AVSCOPE_TRANSPORT_STATE -ErrorAction SilentlyContinue

$rtpVideoScreenshot = "$output\rtp-video-payload.png"
$rtpVideoJson = "$output\rtp-video-payload.json"
$rtpVideoState = "$output\rtp-video-payload-state.json"
Remove-Item -LiteralPath $rtpVideoScreenshot, $rtpVideoJson, $rtpVideoState -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "8"
$env:AVSCOPE_TRANSPORT_DETAIL_TAB = "1"
$env:AVSCOPE_RTP_VIDEO_STATE = $rtpVideoState
$env:AVSCOPE_SCREENSHOT = $rtpVideoScreenshot
$rtpVideoProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample_rtp_video.pcap" -WindowStyle Hidden -PassThru
if (-not $rtpVideoProcess.WaitForExit(10000)) {
    $rtpVideoProcess.Kill()
    throw "Qt RTP video payload smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rtpVideoScreenshot)) {
    throw "Qt RTP video payload screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rtpVideoJson -Force
Remove-Item Env:\AVSCOPE_START_TAB, Env:\AVSCOPE_TRANSPORT_DETAIL_TAB, Env:\AVSCOPE_RTP_VIDEO_STATE -ErrorAction SilentlyContinue

$sipSdpScreenshot = "$output\sip-sdp-signaling.png"
$sipSdpJson = "$output\sip-sdp-signaling.json"
$sipSdpState = "$output\sip-sdp-signaling-state.json"
Remove-Item -LiteralPath $sipSdpScreenshot, $sipSdpJson, $sipSdpState -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "8"
$env:AVSCOPE_TRANSPORT_DETAIL_TAB = "3"
$env:AVSCOPE_SIP_SDP_STATE = $sipSdpState
$env:AVSCOPE_SCREENSHOT = $sipSdpScreenshot
$sipSdpProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample_sip_sdp.pcap" -WindowStyle Hidden -PassThru
if (-not $sipSdpProcess.WaitForExit(10000)) {
    $sipSdpProcess.Kill()
    throw "Qt SIP/SDP signaling smoke test timed out"
}
if (-not (Test-Path -LiteralPath $sipSdpScreenshot)) {
    throw "Qt SIP/SDP signaling screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $sipSdpJson -Force
Remove-Item Env:\AVSCOPE_START_TAB, Env:\AVSCOPE_TRANSPORT_DETAIL_TAB, Env:\AVSCOPE_SIP_SDP_STATE -ErrorAction SilentlyContinue

$rtcpFeedbackScreenshot = "$output\rtcp-feedback.png"
$rtcpFeedbackJson = "$output\rtcp-feedback.json"
$rtcpFeedbackState = "$output\rtcp-feedback-state.json"
Remove-Item -LiteralPath $rtcpFeedbackScreenshot, $rtcpFeedbackJson, $rtcpFeedbackState -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "8"
$env:AVSCOPE_TRANSPORT_DETAIL_TAB = "4"
$env:AVSCOPE_RTCP_FEEDBACK_STATE = $rtcpFeedbackState
$env:AVSCOPE_SCREENSHOT = $rtcpFeedbackScreenshot
$rtcpFeedbackProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample_rtcp_feedback.pcap" -WindowStyle Hidden -PassThru
if (-not $rtcpFeedbackProcess.WaitForExit(10000)) {
    $rtcpFeedbackProcess.Kill()
    throw "Qt RTCP feedback smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rtcpFeedbackScreenshot)) {
    throw "Qt RTCP feedback screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rtcpFeedbackJson -Force
Remove-Item Env:\AVSCOPE_START_TAB, Env:\AVSCOPE_TRANSPORT_DETAIL_TAB, Env:\AVSCOPE_RTCP_FEEDBACK_STATE -ErrorAction SilentlyContinue

$codecH264Screenshot = "$output\codec-health-h264.png"
$codecH264Json = "$output\codec-health-h264.json"
$codecH264State = "$output\codec-health-h264-state.json"
Remove-Item -LiteralPath $codecH264Screenshot, $codecH264Json, $codecH264State -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "9"
$env:AVSCOPE_THEME = "dark"
$env:AVSCOPE_CODEC_HEALTH_STATE = $codecH264State
$env:AVSCOPE_SCREENSHOT = $codecH264Screenshot
$codecH264Process = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample_h264_issues.h264" -WindowStyle Hidden -PassThru
if (-not $codecH264Process.WaitForExit(10000)) {
    $codecH264Process.Kill()
    throw "Qt H.264 codec health smoke test timed out"
}
if (-not (Test-Path -LiteralPath $codecH264Screenshot)) {
    throw "Qt H.264 codec health screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $codecH264Json -Force

$codecH265Screenshot = "$output\codec-health-h265.png"
$codecH265Json = "$output\codec-health-h265.json"
$codecH265State = "$output\codec-health-h265-state.json"
Remove-Item -LiteralPath $codecH265Screenshot, $codecH265Json, $codecH265State -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_THEME = "light"
$env:AVSCOPE_CODEC_HEALTH_STATE = $codecH265State
$env:AVSCOPE_SCREENSHOT = $codecH265Screenshot
$codecH265Process = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample_h265_issues.h265" -WindowStyle Hidden -PassThru
if (-not $codecH265Process.WaitForExit(10000)) {
    $codecH265Process.Kill()
    throw "Qt H.265 codec health smoke test timed out"
}
if (-not (Test-Path -LiteralPath $codecH265Screenshot)) {
    throw "Qt H.265 codec health screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $codecH265Json -Force
Remove-Item Env:\AVSCOPE_START_TAB, Env:\AVSCOPE_CODEC_HEALTH_STATE -ErrorAction SilentlyContinue
$env:AVSCOPE_THEME = "dark"

$diagnosticScreenshot = "$output\diagnostic-filter.png"
$diagnosticJson = "$output\diagnostic-filter.json"
$diagnosticState = "$output\diagnostic-filter-state.json"
$diagnosticSample = "$root\tmp\qt-ui-validation\chunk-offset-invalid.mp4"
Remove-Item -LiteralPath $diagnosticScreenshot, $diagnosticJson, $diagnosticState, $diagnosticSample -Force -ErrorAction SilentlyContinue
$env:PYTHONPATH = $root
& "E:\DevelopmentEnvironment\python\python.exe" -c "from pathlib import Path; source=Path(r'$root/samples/sample.mp4'); data=bytearray(source.read_bytes()); marker=data.index(b'stco'); offset=marker+12; data[offset:offset+4]=(8).to_bytes(4,'big'); Path(r'$diagnosticSample').write_bytes(data)"
if ($LASTEXITCODE -ne 0) { throw "Qt diagnostic fixture generation failed" }
$env:AVSCOPE_DIAGNOSTIC_SEVERITY = "warning"
$env:AVSCOPE_DIAGNOSTIC_OFFSET_ONLY = "1"
$env:AVSCOPE_DIAGNOSTIC_STATE = $diagnosticState
$env:AVSCOPE_START_TAB = "0"
$env:AVSCOPE_SCREENSHOT = $diagnosticScreenshot
$diagnosticProcess = Start-Process -FilePath $executable -ArgumentList $diagnosticSample -WindowStyle Hidden -PassThru
if (-not $diagnosticProcess.WaitForExit(10000)) {
    $diagnosticProcess.Kill()
    throw "Qt diagnostic filter smoke test timed out"
}
if (-not (Test-Path -LiteralPath $diagnosticScreenshot)) {
    throw "Qt diagnostic filter screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $diagnosticJson -Force
Remove-Item Env:\AVSCOPE_DIAGNOSTIC_SEVERITY, Env:\AVSCOPE_DIAGNOSTIC_OFFSET_ONLY, Env:\AVSCOPE_DIAGNOSTIC_STATE, Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue

$streamsScreenshot = "$output\media-streams.png"
$streamsJson = "$output\media-streams.json"
Remove-Item -LiteralPath $streamsScreenshot, $streamsJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_START_TAB = "5"
$env:AVSCOPE_SCREENSHOT = $streamsScreenshot
$streamsProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.wav" -WindowStyle Hidden -PassThru
if (-not $streamsProcess.WaitForExit(10000)) {
    $streamsProcess.Kill()
    throw "Qt media streams smoke test timed out"
}
if (-not (Test-Path -LiteralPath $streamsScreenshot)) {
    throw "Qt media streams screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $streamsJson -Force
Remove-Item Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue

$rawPcmScreenshot = "$output\raw-pcm.png"
$rawPcmJson = "$output\raw-pcm.json"
Remove-Item -LiteralPath $rawPcmScreenshot, $rawPcmJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_RAW_SAMPLE_RATE = "8000"
$env:AVSCOPE_RAW_CHANNELS = "1"
$env:AVSCOPE_RAW_BITS = "16"
$env:AVSCOPE_RAW_ENDIAN = "little"
$env:AVSCOPE_START_TAB = "4"
$env:AVSCOPE_SCREENSHOT = $rawPcmScreenshot
$rawPcmProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.pcm" -WindowStyle Hidden -PassThru
if (-not $rawPcmProcess.WaitForExit(10000)) {
    $rawPcmProcess.Kill()
    throw "Qt Raw PCM smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rawPcmScreenshot)) {
    throw "Qt Raw PCM screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rawPcmJson -Force

Remove-Item Env:\AVSCOPE_RAW_SAMPLE_RATE, Env:\AVSCOPE_RAW_CHANNELS, Env:\AVSCOPE_RAW_BITS, Env:\AVSCOPE_RAW_ENDIAN -ErrorAction SilentlyContinue
$rawYuvScreenshot = "$output\raw-yuv.png"
$rawYuvJson = "$output\raw-yuv.json"
Remove-Item -LiteralPath $rawYuvScreenshot, $rawYuvJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_RAW_WIDTH = "64"
$env:AVSCOPE_RAW_HEIGHT = "48"
$env:AVSCOPE_RAW_PIXEL_FORMAT = "yuv420p"
$env:AVSCOPE_RAW_FPS = "30"
$env:AVSCOPE_SCREENSHOT = $rawYuvScreenshot
$rawYuvProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.yuv" -WindowStyle Hidden -PassThru
if (-not $rawYuvProcess.WaitForExit(10000)) {
    $rawYuvProcess.Kill()
    throw "Qt Raw YUV smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rawYuvScreenshot)) {
    throw "Qt Raw YUV screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rawYuvJson -Force

$rawYuvNextScreenshot = "$output\raw-yuv-frame-2.png"
$rawYuvNextJson = "$output\raw-yuv-frame-2.json"
Remove-Item -LiteralPath $rawYuvNextScreenshot, $rawYuvNextJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_PREVIEW_STEP = "1"
$env:AVSCOPE_SCREENSHOT = $rawYuvNextScreenshot
$rawYuvNextProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.yuv" -WindowStyle Hidden -PassThru
if (-not $rawYuvNextProcess.WaitForExit(10000)) {
    $rawYuvNextProcess.Kill()
    throw "Qt Raw YUV frame navigation smoke test timed out"
}
if (-not (Test-Path -LiteralPath $rawYuvNextScreenshot)) {
    throw "Qt Raw YUV second-frame screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\current-analysis.json" -Destination $rawYuvNextJson -Force
Remove-Item Env:\AVSCOPE_PREVIEW_STEP -ErrorAction SilentlyContinue

Remove-Item Env:\AVSCOPE_RAW_WIDTH, Env:\AVSCOPE_RAW_HEIGHT, Env:\AVSCOPE_RAW_PIXEL_FORMAT, Env:\AVSCOPE_RAW_FPS, Env:\AVSCOPE_START_TAB -ErrorAction SilentlyContinue
$snapshotPath = "$output\sample-mp4.avscope.json"
$snapshotScreenshot = "$output\project-snapshot.png"
Remove-Item -LiteralPath $snapshotPath, $snapshotScreenshot -Force -ErrorAction SilentlyContinue
$env:PYTHONPATH = $root
& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; from avscope.analyzer import Analyzer; from avscope.report import export_json; source=Path(r'$root/samples/sample.mp4'); report=Path(r'$output/snapshot-analysis.json'); export_json(Analyzer().analyze(source),report); analysis=json.loads(report.read_text(encoding='utf-8')); bookmarks=[{'offset':24,'note':'ftyp size','location':'ftyp'},{'offset':539,'note':'mdat payload','location':'mdat'}]; snapshot={'schema_version':1,'source_path':str(source),'theme':'light','current_tab':6,'raw_options':[],'bookmarks':bookmarks,'analysis':analysis}; Path(r'$snapshotPath').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding='utf-8')"
if ($LASTEXITCODE -ne 0) { throw "Qt project snapshot fixture generation failed" }
$env:AVSCOPE_SCREENSHOT = $snapshotScreenshot
$snapshotProcess = Start-Process -FilePath $executable -ArgumentList $snapshotPath -WindowStyle Hidden -PassThru
if (-not $snapshotProcess.WaitForExit(10000)) {
    $snapshotProcess.Kill()
    throw "Qt project snapshot restore smoke test timed out"
}
if (-not (Test-Path -LiteralPath $snapshotScreenshot)) {
    throw "Qt project snapshot screenshot was not generated"
}
$compareScreenshot = "$output\compare-protocol.png"
$compareJson = "$output\compare-protocol.json"
Remove-Item -LiteralPath $compareScreenshot, $compareJson -Force -ErrorAction SilentlyContinue
$env:AVSCOPE_COMPARE_MODE = "protocol"
$env:AVSCOPE_COMPARE_PATH = "$root\samples\sample_changed.mp4"
$env:AVSCOPE_SCREENSHOT = $compareScreenshot
$compareProcess = Start-Process -FilePath $executable -ArgumentList "$root\samples\sample.mp4" -WindowStyle Hidden -PassThru
if (-not $compareProcess.WaitForExit(10000)) {
    $compareProcess.Kill()
    throw "Qt protocol compare smoke test timed out"
}
if (-not (Test-Path -LiteralPath $compareScreenshot)) {
    throw "Qt protocol compare screenshot was not generated"
}
Copy-Item -LiteralPath "$root\tmp\qt-runtime\compare-protocol.json" -Destination $compareJson -Force
Remove-Item Env:\AVSCOPE_COMPARE_MODE, Env:\AVSCOPE_COMPARE_PATH -ErrorAction SilentlyContinue
Remove-Item Env:\AVSCOPE_WINDOW_WIDTH, Env:\AVSCOPE_WINDOW_HEIGHT -ErrorAction SilentlyContinue

$env:PYTHONPATH = $root
& "E:\DevelopmentEnvironment\python\python.exe" -c "from pathlib import Path; from avscope.ffmpeg_preview import png_dimensions; paths=[Path(r'$output/dark.png'),Path(r'$output/light.png'),Path(r'$output/timeline-pcap.png'),Path(r'$output/pcap-rtcp-preview.png'),Path(r'$output/transport-sessions.png'),Path(r'$output/rtp-video-payload.png'),Path(r'$output/sip-sdp-signaling.png'),Path(r'$output/rtcp-feedback.png'),Path(r'$output/codec-health-h264.png'),Path(r'$output/codec-health-h265.png'),Path(r'$output/media-streams.png'),Path(r'$output/diagnostic-filter.png'),Path(r'$output/raw-pcm.png'),Path(r'$output/raw-yuv.png'),Path(r'$output/raw-yuv-frame-2.png'),Path(r'$output/project-snapshot.png'),Path(r'$output/compare-protocol.png')]; dims=[png_dimensions(p) for p in paths]; assert len(set(dims)) == 1, dims; width,height=dims[0]; assert width >= 1560 and height >= 940, dims; assert abs(width / height - 1560 / 940) < 0.01, dims; assert all(p.stat().st_size > 50000 for p in paths), [(p.name,p.stat().st_size) for p in paths]; compact=Path(r'$compactScreenshot'); compact_dims=png_dimensions(compact); assert compact_dims == (1680,1080), compact_dims; assert compact.stat().st_size > 40000; settings=Path(r'$root/data/qt-settings.ini'); assert settings.exists() and settings.stat().st_size > 0; print({'screenshots': [str(p) for p in paths], 'dimensions': dims, 'compact': {'path': str(compact), 'dimensions': compact_dims}, 'dpi_scale': round(width / 1560, 2), 'settings': str(settings)})"
if ($LASTEXITCODE -ne 0) { throw "Qt screenshot validation failed" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$root/tmp/qt-runtime/current-analysis.json').read_text(encoding='utf-8')); root=document['root']; assert root['children'] and root['children'][0]['fields']; streams=json.loads(Path(r'$streamsJson').read_text(encoding='utf-8'))['media']['summary']['ffprobe']['streams']; assert len(streams)==1 and streams[0]['codec_name']=='pcm_s16le' and streams[0]['sample_rate']=='8000', streams; diagnostic=json.loads(Path(r'$diagnosticJson').read_text(encoding='utf-8')); issues=[i for i in diagnostic['diagnostics'] if i['severity']=='warning' and i.get('offset') is not None]; assert issues and any('chunk offset' in i['message'] for i in issues), issues; state=json.loads(Path(r'$diagnosticState').read_text(encoding='utf-8')); assert state=={'visible':1,'total':3,'severity':'warning','source':'all','offset_only':True}, state; pcm=json.loads(Path(r'$rawPcmJson').read_text(encoding='utf-8'))['media']['summary']; assert (pcm['sample_rate'],pcm['channels'],pcm['bits_per_sample'],pcm['endian']) == (8000,1,16,'little'), pcm; yuv=json.loads(Path(r'$rawYuvJson').read_text(encoding='utf-8'))['media']['summary']; assert (yuv['width'],yuv['height'],yuv['pixel_format'],yuv['fps'],yuv['frames']) == (64,48,'yuv420p',30.0,3), yuv; yuv_next=json.loads(Path(r'$rawYuvNextJson').read_text(encoding='utf-8'))['media']['summary']['yuv_preview']; assert yuv_next['frame_index']==1 and yuv_next['total_frames']==3, yuv_next; snapshot=json.loads(Path(r'$snapshotPath').read_text(encoding='utf-8')); assert snapshot['analysis']['root']['children'] and snapshot['source_path'].endswith('sample.mp4') and len(snapshot['bookmarks'])==2; compare=json.loads(Path(r'$compareJson').read_text(encoding='utf-8')); assert len(compare['added']) == 1 and len(compare['changed']) >= 1, compare; print({'nodes': len(root['children']), 'first_fields': len(root['children'][0]['fields']), 'media_streams': streams, 'diagnostic_filter': state, 'raw_pcm': {k:pcm[k] for k in ('sample_rate','channels','bits_per_sample','endian')}, 'raw_yuv': {k:yuv[k] for k in ('width','height','pixel_format','fps','frames')}, 'yuv_navigation': yuv_next['frame_index'], 'project_snapshot': {'source':snapshot['source_path'],'bookmarks':len(snapshot['bookmarks'])}, 'protocol_compare': {k:len(compare[k]) for k in ('added','removed','changed')}})"
if ($LASTEXITCODE -ne 0) { throw "Qt protocol tree data contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from collections import Counter; from pathlib import Path; document=json.loads(Path(r'$rtcpPreviewJson').read_text(encoding='utf-8')); summary=document['media']['summary']; rtcp=summary['rtcp']; walk=lambda node:[node]+[item for child in node.get('children',[]) for item in walk(child)]; nodes=walk(document['root']); types=Counter(node['node_type'] for node in nodes); assert (summary['packets'],summary['rtp_packets'],summary['rtcp_packets'])==(3,2,2), summary; assert (rtcp['sender_reports'],rtcp['receiver_reports'],rtcp['report_blocks'])==(1,1,2), rtcp; assert rtcp['max_interarrival_jitter']==90 and rtcp['max_delay_since_last_sr_seconds']==0.5, rtcp; required={'ethernet':3,'ipv4':3,'udp':3,'rtp':2,'rtcp_compound':1,'rtcp_packet':2,'rtcp_report_block':2}; assert all(types[key]==value for key,value in required.items()), (types,required); assert all(node.get('fields') for node in nodes if node['node_type'] in required), types; print({'pcap': {k:summary[k] for k in ('packets','rtp_packets','rtcp_packets')}, 'rtcp': rtcp, 'node_types': dict(types)})"
if ($LASTEXITCODE -ne 0) { throw "Qt RTCP protocol tree or preview contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$transportJson').read_text(encoding='utf-8')); transport=document['media']['summary']['transport_sessions']; state=json.loads(Path(r'$transportState').read_text(encoding='utf-8')); assert (transport['session_count'],transport['warning_sessions'])==(2,1), transport; assert (transport['estimated_lost_packets'],transport['duplicate_packets'],transport['reordered_packets'])==(1,1,1), transport; warning=next(item for item in transport['sessions'] if item['status']=='warning'); clean=next(item for item in transport['sessions'] if item['status']=='normal'); assert warning['ssrc']=='0x12345678' and clean['ssrc']=='0xABCDEF01', transport; assert state=={'visible':1,'total':2,'issues_only':True}, state; print({'transport': {k:transport[k] for k in ('session_count','warning_sessions','estimated_lost_packets','duplicate_packets','reordered_packets')}, 'filter':state, 'warning_ssrc':warning['ssrc']})"
if ($LASTEXITCODE -ne 0) { throw "Qt transport session table or filter contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$rtpVideoJson').read_text(encoding='utf-8')); summary=document['media']['summary']; video=summary['rtp_video']; transport=summary['transport_sessions']; state=json.loads(Path(r'$rtpVideoState').read_text(encoding='utf-8')); assert video['codecs']==['H.264','H.265'] and (video['stream_count'],video['warning_streams'])==(3,1), video; assert (video['packets'],video['nal_units'],video['completed_fragments'],video['incomplete_fragments'])==(9,6,2,1), video; assert len(video['issues'])==1 and video['issues'][0]['source']=='rtp_video' and video['issues'][0]['offset']>0, video; assert transport['warning_sessions']==1 and transport['video_warning_streams']==1, transport; assert state=={'streams':3,'issues':1,'nal_units':6,'completed_fragments':2,'incomplete_fragments':1,'codecs':['H.264','H.265']}, state; print({'rtp_video':state,'issue':video['issues'][0]})"
if ($LASTEXITCODE -ne 0) { throw "Qt RTP H.264/H.265 payload page contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$sipSdpJson').read_text(encoding='utf-8')); summary=document['media']['summary']; signaling=summary['sip_sdp']; video=summary['rtp_video']; transport=summary['transport_sessions']; state=json.loads(Path(r'$sipSdpState').read_text(encoding='utf-8')); assert (signaling['message_count'],signaling['call_count'],signaling['media_count'],signaling['mapping_count'],signaling['unique_mapping_count'])==(3,2,5,7,4), signaling; assert {(item['port'],item['encoding']) for item in signaling['unique_payload_mappings'] if item['payload_type']==96}=={(5004,'H264'),(6004,'H265')}; assert video['codecs']==['H.264','H.265'] and video['stream_count']==2, video; assert transport['sdp_linked_sessions']==3, transport; audio=next(frame for frame in document['frames'] if frame['metadata'].get('rtp_negotiated_encoding')=='PCMA'); assert audio['pts']==1.0 and audio['metadata']['rtp_clock_rate']==8000 and not audio['metadata']['rtp_video_codec'], audio; assert state=={'messages':3,'calls':2,'media':5,'mappings':4,'issues':0}, state; print({'sip_sdp':state,'video_codecs':video['codecs'],'audio_pts':audio['pts']})"
if ($LASTEXITCODE -ne 0) { throw "Qt SIP/SDP signaling and dynamic payload mapping contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; document=json.loads(Path(r'$rtcpFeedbackJson').read_text(encoding='utf-8')); summary=document['media']['summary']; rtcp=summary['rtcp']; transport=summary['transport_sessions']; state=json.loads(Path(r'$rtcpFeedbackState').read_text(encoding='utf-8')); assert state=={'feedback':3,'nack':1,'lost_sequences':3,'pli':1,'fir':1,'sdes':1,'bye':1}, state; assert rtcp['feedback_events'][0]['lost_sequences']==[101,103,105] and rtcp['feedback_events'][2]['fir_sequence']==7, rtcp; session=transport['sessions'][0]; assert session['rtcp_cname']=='camera-01@example' and session['rtcp_bye_reason']=='stream ended' and session['status']=='warning', session; print({'rtcp_feedback':state,'cname':session['rtcp_cname'],'bye_reason':session['rtcp_bye_reason']})"
if ($LASTEXITCODE -ne 0) { throw "Qt RTCP feedback page or session link contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; h264=json.loads(Path(r'$codecH264Json').read_text(encoding='utf-8'))['media']['summary']['codec_health']; h265=json.loads(Path(r'$codecH265Json').read_text(encoding='utf-8'))['media']['summary']['codec_health']; s264=json.loads(Path(r'$codecH264State').read_text(encoding='utf-8')); s265=json.loads(Path(r'$codecH265State').read_text(encoding='utf-8')); assert h264['issue_count']==4 and h264['missing_pps_ids']==[7] and h264['missing_sps_ids']==[9], h264; assert h264['resolution_changes'][0]['from_width']==640 and h264['resolution_changes'][0]['to_width']==320, h264; assert h265['issue_count']==5 and h265['missing_pps_ids']==[7] and h265['missing_sps_ids']==[8] and h265['missing_vps_ids']==[9], h265; assert h265['resolution_changes'][0]['from_width']==640 and h265['resolution_changes'][0]['to_width']==1280, h265; assert s264=={'available':True,'codec':'H.264 Annex-B','status':'warning','issues':4,'parameter_rows':3,'resolution_events':2,'resolution_changes':1}, s264; assert s265=={'available':True,'codec':'H.265 Annex-B','status':'warning','issues':5,'parameter_rows':4,'resolution_events':2,'resolution_changes':1}, s265; print({'h264':s264,'h265':s265})"
if ($LASTEXITCODE -ne 0) { throw "Qt H.26x codec health page contract is incomplete" }

& "E:\DevelopmentEnvironment\python\python.exe" -c "import json; from pathlib import Path; pcm=json.loads(Path(r'$rawPcmJson').read_text(encoding='utf-8'))['media']['summary']; yuv=json.loads(Path(r'$rawYuvJson').read_text(encoding='utf-8'))['media']['summary']; assert pcm['waveform']['energy']['peak_level'] > 0.5; preview=Path(yuv['yuv_preview']['path']); assert yuv['yuv_preview']['available'] and preview.exists() and preview.stat().st_size > 100; source=Path(r'$root/qt/src/MainWindow.cpp').read_text(encoding='utf-8'); assert 'waitForFinished' not in source; print({'pcm_peak': pcm['waveform']['energy']['peak_level'], 'yuv_preview': str(preview), 'async_tasks': True})"
if ($LASTEXITCODE -ne 0) { throw "Qt media visualization or asynchronous task validation failed" }

Write-Output "Qt UI validation OK"
