' ishga_tushirish.bat ni oynasiz ishga tushiradi (qabulxona kompyuterida oyna tasodifan yopilmasin).
Set sh = CreateObject("WScript.Shell")
dir = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run """" & dir & "\ishga_tushirish.bat""", 0, False
