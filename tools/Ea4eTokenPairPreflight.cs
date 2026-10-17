// Read-only token observation. It neither elevates nor launches a process.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

internal static class Ea4eTokenPairPreflight
{
    private const uint TokenQuery = 0x0008;
    private const int TokenElevationType = 18;
    private const int TokenLinkedToken = 19;
    private const int TokenIntegrityLevel = 25;

    [DllImport("kernel32.dll")]
    private static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool OpenProcessToken(
        IntPtr process, uint access, out SafeFileHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetTokenInformation(
        SafeFileHandle token, int informationClass, IntPtr buffer,
        uint length, out uint returned);

    private static int Main(string[] args)
    {
        if (args.Length != 1 || args[0] != "SELF") return 2;
        SafeFileHandle token;
        if (!OpenProcessToken(GetCurrentProcess(), TokenQuery, out token))
            return 3;
        using (token)
        {
            int elevation;
            string integrity;
            if (!ReadElevation(token, out elevation)
                || !ReadIntegrity(token, out integrity))
                return 4;
            Console.WriteLine("CURRENT_ELEVATION_TYPE=" + elevation);
            Console.WriteLine("CURRENT_INTEGRITY_SID=" + integrity);

            IntPtr buffer = Marshal.AllocHGlobal(IntPtr.Size);
            try
            {
                uint returned;
                if (!GetTokenInformation(token, TokenLinkedToken, buffer,
                    (uint)IntPtr.Size, out returned) || returned != IntPtr.Size)
                {
                    Console.WriteLine("LINKED_TOKEN=UNAVAILABLE");
                    return 0;
                }
                IntPtr linkedHandle = Marshal.ReadIntPtr(buffer);
                if (linkedHandle == IntPtr.Zero)
                    return 5;
                using (var linked = new SafeFileHandle(linkedHandle, true))
                {
                    int linkedElevation;
                    string linkedIntegrity;
                    if (!ReadElevation(linked, out linkedElevation)
                        || !ReadIntegrity(linked, out linkedIntegrity))
                        return 6;
                    Console.WriteLine("LINKED_TOKEN=OBSERVED");
                    Console.WriteLine("LINKED_ELEVATION_TYPE=" + linkedElevation);
                    Console.WriteLine("LINKED_INTEGRITY_SID=" + linkedIntegrity);
                }
                return 0;
            }
            finally
            {
                Marshal.FreeHGlobal(buffer);
            }
        }
    }

    private static bool ReadElevation(SafeFileHandle token, out int elevation)
    {
        IntPtr buffer = Marshal.AllocHGlobal(sizeof(int));
        elevation = 0;
        try
        {
            uint returned;
            if (!GetTokenInformation(token, TokenElevationType, buffer,
                sizeof(int), out returned) || returned != sizeof(int))
                return false;
            elevation = Marshal.ReadInt32(buffer);
            return elevation >= 1 && elevation <= 3;
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }

    private static bool ReadIntegrity(SafeFileHandle token, out string integrity)
    {
        integrity = null;
        uint required;
        GetTokenInformation(token, TokenIntegrityLevel, IntPtr.Zero, 0,
            out required);
        if (required < IntPtr.Size || required > 4096) return false;
        IntPtr buffer = Marshal.AllocHGlobal((int)required);
        try
        {
            uint returned;
            if (!GetTokenInformation(token, TokenIntegrityLevel, buffer,
                required, out returned) || returned != required)
                return false;
            IntPtr sid = Marshal.ReadIntPtr(buffer);
            if (sid == IntPtr.Zero) return false;
            integrity = new SecurityIdentifier(sid).Value;
            return integrity.StartsWith("S-1-16-", StringComparison.Ordinal);
        }
        finally
        {
            Marshal.FreeHGlobal(buffer);
        }
    }
}
