// Source-only SECURITY_ATTRIBUTES marshalling; no native create call site.
using System;
using System.Runtime.InteropServices;
using System.Security.AccessControl;

internal static class Ea4eDirectory2SecurityAttributesCandidate
{
    [StructLayout(LayoutKind.Sequential)]
    internal struct SecurityAttributes
    {
        internal int Length;
        internal IntPtr Descriptor;
        internal int InheritHandle;
    }

    internal static bool HasExpectedLayout()
    {
        Type type = typeof(SecurityAttributes);
        int pointer = IntPtr.Size;
        return (pointer == 4 || pointer == 8) &&
            Marshal.OffsetOf(type, "Length").ToInt32() == 0 &&
            Marshal.OffsetOf(type, "Descriptor").ToInt32() == pointer &&
            Marshal.OffsetOf(type, "InheritHandle").ToInt32() == 2 * pointer &&
            Marshal.SizeOf(type) == (pointer == 8 ? 24 : 12);
    }

    internal static string Inspect(string sddl, string appSid,
                                   Func<IntPtr, string> observer)
    {
        if (observer == null) return "DENY:OBSERVER_MISSING";
        if (!HasExpectedLayout()) return "DENY:STRUCT_LAYOUT";
        if (Ea4eAnnouncementFileDescriptorCandidate.ScreenDirectorySddl(
                sddl, appSid) !=
            "CANDIDATE:DIRECTORY_DESCRIPTOR_STRUCTURE_ONLY")
            return "DENY:DESCRIPTOR";
        var raw = new RawSecurityDescriptor(sddl);
        byte[] bytes = new byte[raw.BinaryLength];
        raw.GetBinaryForm(bytes, 0);
        if (bytes.Length < 20 || bytes.Length > 8192)
            return "DENY:DESCRIPTOR_SIZE";

        IntPtr descriptor = IntPtr.Zero;
        IntPtr attributes = IntPtr.Zero;
        try
        {
            descriptor = Marshal.AllocHGlobal(bytes.Length);
            Marshal.Copy(bytes, 0, descriptor, bytes.Length);
            var value = new SecurityAttributes {
                Length = Marshal.SizeOf(typeof(SecurityAttributes)),
                Descriptor = descriptor,
                InheritHandle = 0,
            };
            attributes = Marshal.AllocHGlobal(value.Length);
            Marshal.StructureToPtr(value, attributes, false);
            return observer(attributes);
        }
        finally
        {
            if (attributes != IntPtr.Zero) Marshal.FreeHGlobal(attributes);
            if (descriptor != IntPtr.Zero) Marshal.FreeHGlobal(descriptor);
        }
    }
}
