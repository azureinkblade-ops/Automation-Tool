using System;

internal static class Probe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "--info-class")
        {
            Console.WriteLine(Ea4eAnnouncementFileIdentityCandidate.RequestedInfoClass());
            return 0;
        }
        if (args.Length == 2 && args[0] == "--screen")
        {
            byte[] fileId;
            ulong volume;
            if (!UInt64.TryParse(args[1], out volume)) return 2;
            fileId = new byte[16];
            fileId[0] = 0x12;
            fileId[15] = 0xab;
            string volumeHex, fileIdHex;
            string result = Ea4eAnnouncementFileIdentityCandidate.Screen(
                volume, fileId, out volumeHex, out fileIdHex);
            Console.WriteLine(result);
            if (result == "CANDIDATE:FILE_ID_ONLY")
                Console.WriteLine(volumeHex + ":" + fileIdHex);
            return 0;
        }
        return 2;
    }
}
