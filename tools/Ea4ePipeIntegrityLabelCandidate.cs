// Read-only label observation on an already-open pipe; no issuer authority.
using System;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

internal static class Ea4ePipeIntegrityLabelCandidate
{
    private const uint LabelSecurityInformation = 0x10;
    private const byte MandatoryLabelAceType = 0x11;
    private const int SeFileObject = 1;

    [DllImport("advapi32.dll")]
    private static extern uint GetSecurityInfo(
        SafePipeHandle handle, int objectType, uint securityInformation,
        out IntPtr owner, out IntPtr group, out IntPtr dacl,
        out IntPtr sacl, out IntPtr descriptor);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetSecurityDescriptorSacl(
        IntPtr descriptor, [MarshalAs(UnmanagedType.Bool)] out bool present,
        out IntPtr sacl, [MarshalAs(UnmanagedType.Bool)] out bool defaulted);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetAce(IntPtr acl, uint index, out IntPtr ace);

    [DllImport("kernel32.dll")]
    private static extern IntPtr LocalFree(IntPtr memory);

    internal static string Observe(SafePipeHandle pipe)
    {
        if (pipe == null || pipe.IsInvalid || pipe.IsClosed)
            return "DENY:PIPE_HANDLE_UNAVAILABLE";
        IntPtr owner, group, dacl, sacl, descriptor;
        uint error = GetSecurityInfo(pipe, SeFileObject, LabelSecurityInformation,
            out owner, out group, out dacl, out sacl, out descriptor);
        if (error != 0 || descriptor == IntPtr.Zero)
            return "DENY:LABEL_READBACK_FAILED";
        try
        {
            bool present, defaulted;
            if (!GetSecurityDescriptorSacl(descriptor, out present, out sacl,
                out defaulted))
                return "DENY:LABEL_DESCRIPTOR_INVALID";
            if (!present || sacl == IntPtr.Zero)
                return "OBSERVED:UNLABELED";
            int count = (ushort)Marshal.ReadInt16(sacl, 4);
            string label = null;
            for (uint i = 0; i < count; i++)
            {
                IntPtr ace;
                if (!GetAce(sacl, i, out ace))
                    return "DENY:LABEL_ACE_UNAVAILABLE";
                if (Marshal.ReadByte(ace) != MandatoryLabelAceType)
                    continue;
                if (label != null)
                    return "DENY:MULTIPLE_LABELS";
                try
                {
                    string sid = new SecurityIdentifier(IntPtr.Add(ace, 8)).Value;
                    uint policy = (uint)Marshal.ReadInt32(ace, 4);
                    label = "OBSERVED:" + sid + ":" + policy.ToString("X8");
                }
                catch (ArgumentException)
                {
                    return "DENY:LABEL_SID_INVALID";
                }
            }
            return label ?? "OBSERVED:UNLABELED";
        }
        finally
        {
            LocalFree(descriptor);
        }
    }
}
