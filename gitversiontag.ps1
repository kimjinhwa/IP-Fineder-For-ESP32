$content = Get-Content .\Version.h  -Encoding utf8 -TotalCount 1
if ($content -match '#define version "(.*?)".*\/\/(.*)')
{
    $version = $matches[1].Trim()    # "SBMS_1.0.0" 추출
    $comment = $matches[2].Trim()    # "Release Version 1.0.0" 추출
    $currentBranch = git rev-parse --abbrev-ref HEAD

    # PyInstaller로 실행 파일 생성
    pyinstaller --onefile --windowed --name=IPFinder TcpIpConverterFinder.py

        # dist 폴더의 실행 파일을 압축
    $zipFileName = ".\dist\IPFinder_v$version.zip"
    echo "zipFileName: $zipFileName"
    # 이전 zip 파일이 있다면 삭제
    if (Test-Path $zipFileName) {
        Remove-Item $zipFileName
    }
    # dist 폴더의 실행 파일을 zip으로 압축
    Compress-Archive -Path ".\dist\IPFinder.exe" -DestinationPath $zipFileName
    echo "Created zip file: $zipFileName"
    # 현재 브랜치 이름 가져오기
    
    echo "Version: $version"
    echo "Comment: $comment"
    git add -A
    git commit -am $comment
    git tag -a $version -m $comment
    git push origin $currentBranch --tags
}
else
{
    echo "Version.h 파일을 찾을 수 없습니다."
}