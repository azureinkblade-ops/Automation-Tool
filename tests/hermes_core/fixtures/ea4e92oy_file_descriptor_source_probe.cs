using System;
using System.Security.AccessControl;

internal static class Probe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "flags")
        {
            Console.WriteLine(Ea4eAnnouncementFileDescriptorCandidate
                .RequestedSecurityInformation().ToString("x8"));
            return 0;
        }
        if (args.Length == 3 && args[0] == "screen")
        {
            Console.WriteLine(Ea4eAnnouncementFileDescriptorCandidate
                .ScreenSddl(args[1], args[2]));
            return 0;
        }
        if (args.Length == 3 && (args[0] == "screen-bytes" ||
                                 args[0] == "screen-bytes-extra"))
        {
            try
            {
                var descriptor = new RawSecurityDescriptor(args[1]);
                byte[] bytes = new byte[descriptor.BinaryLength +
                    (args[0] == "screen-bytes-extra" ? 1 : 0)];
                descriptor.GetBinaryForm(bytes, 0);
                Console.WriteLine(Ea4eAnnouncementFileDescriptorCandidate
                    .ScreenBytes(bytes, args[2]));
            }
            catch (SystemException) { Console.WriteLine("DENY:INVALID_DESCRIPTOR"); }
            return 0;
        }
        return 2;
    }
}
