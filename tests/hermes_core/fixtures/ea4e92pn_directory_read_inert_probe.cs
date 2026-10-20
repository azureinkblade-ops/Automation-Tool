using System;
using Microsoft.Win32.SafeHandles;

internal static class Ea4e92pnDirectoryReadInertProbe
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        byte[] bytes;
        string result;
        SafeFileHandle handle = null;
        if (args[0] == "zero") handle = new SafeFileHandle(IntPtr.Zero, false);
        else if (args[0] == "invalid")
            handle = new SafeFileHandle(new IntPtr(-1), false);
        if (args[0] == "directory" || args[0] == "zero" ||
            args[0] == "invalid")
            result = Ea4eAnnouncementFileDescriptorCandidate.ReadDirectory(
                handle, "S-1-5-21-100-200-300-1001", out bytes);
        else if (args[0] == "file")
            result = Ea4eAnnouncementFileDescriptorCandidate.Read(
                null, "S-1-5-21-100-200-300-1001", out bytes);
        else return 2;
        Console.WriteLine(result);
        Console.WriteLine(bytes == null ? "NO_BYTES" : "UNEXPECTED_BYTES");
        return 0;
    }
}
