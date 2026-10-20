using System;

internal static class Ea4e92pdKnownFolderProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1 || args[0] != "--resolve") return 2;
        string path;
        string denial = Ea4eProgramDataKnownFolderCandidate.Resolve(out path);
        Console.WriteLine(denial ?? "CANDIDATE:KNOWN_FOLDER_PATH_ONLY:" + path);
        return denial == null ? 0 : 1;
    }
}
