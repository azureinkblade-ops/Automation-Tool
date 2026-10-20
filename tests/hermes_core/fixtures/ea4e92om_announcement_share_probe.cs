using System;
using System.Globalization;

internal static class Ea4e92omAnnouncementShareProbe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "masks")
        {
            Console.WriteLine("{0:x8},{1:x8},{2:x8},{3:x8}",
                Ea4eAnnouncementSharePolicyCandidate.CreatorDesiredAccess(),
                Ea4eAnnouncementSharePolicyCandidate.CreatorShareMode(),
                Ea4eAnnouncementSharePolicyCandidate.ReaderDesiredAccess(),
                Ea4eAnnouncementSharePolicyCandidate.ReaderShareMode());
            return 0;
        }
        if (args.Length != 5 || args[0] != "screen") return 2;
        uint[] values = new uint[4];
        for (int index = 0; index < values.Length; index++)
            if (!UInt32.TryParse(args[index + 1], NumberStyles.HexNumber,
                CultureInfo.InvariantCulture, out values[index])) return 2;
        Console.WriteLine(Ea4eAnnouncementSharePolicyCandidate.Screen(
            values[0], values[1], values[2], values[3]));
        return 0;
    }
}
