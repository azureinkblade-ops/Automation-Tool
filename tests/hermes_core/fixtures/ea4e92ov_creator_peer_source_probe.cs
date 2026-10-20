using System;

internal static class Probe
{
    private static int Main(string[] args)
    {
        if (args.Length == 6 && args[0] == "screen")
        {
            uint expectedPid, launchPid, clientPid;
            ulong expectedTime, launchTime;
            bool alive;
            if (!UInt32.TryParse(args[1], out expectedPid) ||
                !UInt64.TryParse(args[2], out expectedTime) ||
                !UInt32.TryParse(args[3], out launchPid) ||
                !UInt64.TryParse(args[4], out launchTime) ||
                !UInt32.TryParse(args[5], out clientPid))
                return 2;
            alive = true;
            Console.WriteLine(Ea4eCreatorPeerBindingCandidate.Screen(
                expectedPid, expectedTime, launchPid, launchTime,
                clientPid, alive));
            return 0;
        }
        if (args.Length == 7 && args[0] == "screen" &&
            args[6] == "exited")
        {
            uint expectedPid, launchPid, clientPid;
            ulong expectedTime, launchTime;
            if (!UInt32.TryParse(args[1], out expectedPid) ||
                !UInt64.TryParse(args[2], out expectedTime) ||
                !UInt32.TryParse(args[3], out launchPid) ||
                !UInt64.TryParse(args[4], out launchTime) ||
                !UInt32.TryParse(args[5], out clientPid))
                return 2;
            Console.WriteLine(Ea4eCreatorPeerBindingCandidate.Screen(
                expectedPid, expectedTime, launchPid, launchTime,
                clientPid, false));
            return 0;
        }
        return 2;
    }
}
