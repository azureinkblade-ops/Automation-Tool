using System;
using System.Globalization;

internal static class Ea4e92onRetainedReadSourceProbe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "limit")
        {
            Console.WriteLine(Ea4eAnnouncementRetainedReadCandidate.MaximumRecordBytes);
            return 0;
        }
        if (args.Length != 4 || args[0] != "screen") return 2;
        uint attributes;
        uint links;
        ulong size;
        if (!UInt32.TryParse(args[1], NumberStyles.HexNumber,
                CultureInfo.InvariantCulture, out attributes) ||
            !UInt32.TryParse(args[2], NumberStyles.Integer,
                CultureInfo.InvariantCulture, out links) ||
            !UInt64.TryParse(args[3], NumberStyles.Integer,
                CultureInfo.InvariantCulture, out size)) return 2;
        Console.WriteLine(Ea4eAnnouncementRetainedReadCandidate.ScreenShape(
            attributes, links, size));
        return 0;
    }
}
