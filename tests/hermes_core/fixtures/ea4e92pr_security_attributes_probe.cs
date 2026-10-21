using System;
using System.Runtime.InteropServices;
using System.Security.AccessControl;

internal static class Ea4e92prSecurityAttributesProbe
{
    private const string AppSid = "S-1-5-21-100-200-300-1001";
    private const string Sddl = "O:BAG:BAD:P(A;;0x000200a1;;;" + AppSid +
        ")(A;;0x001f01ff;;;SY)(A;;0x001f01ff;;;BA)S:(ML;;NW;;;HI)";

    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string sddl = args[0] == "invalid" ? "D:(A;;GA;;;WD)" : Sddl;
        Func<IntPtr, string> observer = args[0] == "missing"
            ? null : new Func<IntPtr, string>(Observe);
        string result = Ea4eDirectory2SecurityAttributesCandidate.Inspect(
            sddl, AppSid, observer);
        Console.WriteLine(result);
        return 0;
    }

    private static string Observe(IntPtr pointer)
    {
        var value = (Ea4eDirectory2SecurityAttributesCandidate.SecurityAttributes)
            Marshal.PtrToStructure(pointer,
                typeof(Ea4eDirectory2SecurityAttributesCandidate.SecurityAttributes));
        var expected = new RawSecurityDescriptor(Sddl);
        byte[] expectedBytes = new byte[expected.BinaryLength];
        expected.GetBinaryForm(expectedBytes, 0);
        byte[] observed = new byte[expectedBytes.Length];
        Marshal.Copy(value.Descriptor, observed, 0, observed.Length);
        if (value.Length != Marshal.SizeOf(typeof(
                Ea4eDirectory2SecurityAttributesCandidate.SecurityAttributes)) ||
            value.Descriptor == IntPtr.Zero || value.InheritHandle != 0 ||
            !BytesEqual(expectedBytes, observed))
            return "DENY:MARSHALLING";
        return "CANDIDATE:ATTRIBUTES_OBSERVED_ONLY";
    }

    private static bool BytesEqual(byte[] left, byte[] right)
    {
        if (left.Length != right.Length) return false;
        for (int index = 0; index < left.Length; index++)
            if (left[index] != right[index]) return false;
        return true;
    }
}
