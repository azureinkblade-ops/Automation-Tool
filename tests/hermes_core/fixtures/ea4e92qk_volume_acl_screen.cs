using System;
using System.Reflection;

internal static class Ea4e92qkVolumeAclScreen
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        string result;
        if (args[0] == "supported")
            result = Ea4eDirectoryVolumeAclCandidate.Classify(true, 0x00000008);
        else if (args[0] == "supported-plus")
            result = Ea4eDirectoryVolumeAclCandidate.Classify(true, 0x00000009);
        else if (args[0] == "unsupported")
            result = Ea4eDirectoryVolumeAclCandidate.Classify(true, 0x00000001);
        else if (args[0] == "failed-with-bit")
            result = Ea4eDirectoryVolumeAclCandidate.Classify(false, 0x00000008);
        else if (args[0] == "invalid-handle")
        {
            uint flags;
            int error;
            result = Ea4eDirectoryVolumeAclCandidate.Read(null, out flags, out error);
            if (flags != 0 || error != 0) return 3;
        }
        else if (args[0] == "abi")
        {
            MethodInfo native = typeof(Ea4eDirectoryVolumeAclCandidate).GetMethod(
                "GetVolumeInformationByHandleW",
                BindingFlags.NonPublic | BindingFlags.Static);
            if (native == null || native.GetParameters().Length != 8 ||
                native.GetParameters()[5].ParameterType != typeof(uint).MakeByRefType())
                return 3;
            var import = (System.Runtime.InteropServices.DllImportAttribute)
                Attribute.GetCustomAttribute(native,
                    typeof(System.Runtime.InteropServices.DllImportAttribute));
            if (import == null || import.Value != "kernel32.dll" ||
                !import.SetLastError || !import.ExactSpelling) return 3;
            result = "CANDIDATE:DECLARATION_ONLY";
        }
        else return 2;
        Console.WriteLine(result);
        return 0;
    }
}
