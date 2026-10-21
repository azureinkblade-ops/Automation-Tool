using System;

internal static class Ea4e92puRetainedShapeProbe
{
    private const string Expected = @"C:\ProgramData\Hermes\EA4E";
    private const string Final = @"\\?\C:\ProgramData\Hermes\EA4E";

    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        if (args[0] == "null")
        {
            string volume, fileId;
            Console.WriteLine(Ea4eDirectory2RetainedShapeCandidate.Read(
                null, Expected, out volume, out fileId));
            return 0;
        }
        uint type = 1, attributes = 0x10, tagAttributes = 0x10, links = 1;
        string final = Final;
        if (args[0] == "file") attributes = tagAttributes = 0;
        else if (args[0] == "reparse") attributes = tagAttributes = 0x410;
        else if (args[0] == "tag-drift") tagAttributes = 0x410;
        else if (args[0] == "multilink") links = 2;
        else if (args[0] == "pipe") type = 3;
        else if (args[0] == "path") final = @"\\?\C:\ProgramData\Other";
        else if (args[0] == "unc") final = @"\\?\UNC\host\share\EA4E";
        else if (args[0] != "valid") return 2;
        Console.WriteLine(Ea4eDirectory2RetainedShapeCandidate.Screen(
            type, attributes, tagAttributes, links, final, Expected));
        return 0;
    }
}
