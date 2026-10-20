using System;
using System.Security.AccessControl;

internal static class Ea4e92phDirectoryDescriptorProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 3) return 2;
        if (args[0] == "screen")
        {
            Console.WriteLine(Ea4eAnnouncementFileDescriptorCandidate
                .ScreenDirectorySddl(args[1], args[2]));
            return 0;
        }
        if (args[0] == "screen-bytes")
        {
            try
            {
                var descriptor = new RawSecurityDescriptor(args[1]);
                byte[] bytes = new byte[descriptor.BinaryLength];
                descriptor.GetBinaryForm(bytes, 0);
                Console.WriteLine(Ea4eAnnouncementFileDescriptorCandidate
                    .ScreenDirectoryBytes(bytes, args[2]));
            }
            catch (SystemException) { Console.WriteLine("DENY:INVALID_DESCRIPTOR"); }
            return 0;
        }
        return 2;
    }
}
