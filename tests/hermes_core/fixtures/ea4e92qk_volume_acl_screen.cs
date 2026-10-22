using System;
using System.Reflection;
using Microsoft.Win32.SafeHandles;

internal static class Ea4e92qkVolumeAclScreen
{
    private static int Main(string[] args)
    {
        if (args.Length != 1) return 2;
        if (args[0].StartsWith("injected-", StringComparison.Ordinal) ||
            args[0] == "reader-missing" || args[0] == "closed-handle" ||
            args[0] == "invalid-handle-nonnull")
        {
            IntPtr value = args[0] == "invalid-handle-nonnull"
                ? IntPtr.Zero : new IntPtr(123);
            using (var fake = new SafeFileHandle(value, false))
            {
                if (args[0] == "closed-handle") fake.Dispose();
                Ea4eDirectoryVolumeAclCandidate.VolumeInformationReader reader =
                    delegate(SafeFileHandle handle, out uint flags, out int error) {
                        flags = 0;
                        error = 0;
                        if (args[0] == "injected-success")
                        {
                            flags = 8;
                            error = 99;
                            return true;
                        }
                        if (args[0] == "injected-unsupported")
                        {
                            flags = 1;
                            return true;
                        }
                        if (args[0] == "injected-failed-bit")
                        {
                            flags = 8;
                            error = 5;
                            return false;
                        }
                        if (args[0] == "injected-failed-zero")
                        {
                            flags = 8;
                            return false;
                        }
                        if (args[0] == "injected-disposed")
                        {
                            handle.Dispose();
                            throw new ObjectDisposedException("inert handle");
                        }
                        if (args[0] == "injected-dll-missing")
                            throw new DllNotFoundException("inert library");
                        if (args[0] == "injected-entry-missing")
                            throw new EntryPointNotFoundException("inert export");
                        if (args[0] == "injected-throw-after-output")
                        {
                            flags = 8;
                            error = 5;
                            throw new InvalidOperationException("inert partial output");
                        }
                        throw new InvalidOperationException("Unknown inert mode");
                    };
                uint observedFlags;
                int observedError;
                string observed = Ea4eDirectoryVolumeAclCandidate.ReadWith(
                    fake, args[0] == "reader-missing" ? null : reader,
                    out observedFlags, out observedError);
                Console.WriteLine(observed + "|" + observedFlags + "|" +
                    observedError);
                return 0;
            }
        }
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
