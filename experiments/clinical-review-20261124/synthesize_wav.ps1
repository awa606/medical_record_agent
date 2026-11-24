param(
    [Parameter(Mandatory)][string]$Spec,
    [Parameter(Mandatory)][string]$Destination
)
$ErrorActionPreference = 'Stop'
$voice = New-Object -ComObject SAPI.SpVoice
$voice.Rate = 0
$voice.Volume = 100
foreach ($turn in (Get-Content -LiteralPath $Spec -Raw -Encoding utf8 | ConvertFrom-Json)) {
    $token = New-Object -ComObject SAPI.SpObjectToken
    $voicePath = 'HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech_OneCore\Voices\Tokens\MSTTS_V110_zhCN_' + $turn.voice + 'M'
    $token.SetId($voicePath)
    $voice.Voice = $token
    $stream = New-Object -ComObject SAPI.SpFileStream
    $format = New-Object -ComObject SAPI.SpAudioFormat
    $format.Type = 18
    $stream.Format = $format
    $stream.Open((Join-Path $Destination ($turn.id + '.wav')), 3, $false)
    try {
        $voice.AudioOutputStream = $stream
        [void]$voice.Speak($turn.words)
    } finally {
        $stream.Close()
    }
}
