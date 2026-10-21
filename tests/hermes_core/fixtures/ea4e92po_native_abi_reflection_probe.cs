using System;
using System.Reflection;
using System.Runtime.InteropServices;

internal static class Ea4e92poNativeAbiReflectionProbe
{
    private static int Main(string[] args)
    {
        if (args.Length == 1 && args[0] == "wrapper")
        {
            MethodInfo wrapper = typeof(Ea4eDirectory2NativeAbiCandidate)
                .GetMethod("InvokeUnwired", BindingFlags.NonPublic |
                    BindingFlags.Static);
            if (wrapper == null) return 1;
            Console.WriteLine(wrapper.ReturnType.FullName);
            foreach (ParameterInfo parameter in wrapper.GetParameters())
                Console.WriteLine(parameter.ParameterType.FullName);
            return 0;
        }
        if (args.Length != 0) return 2;
        MethodInfo method = typeof(Ea4eDirectory2NativeAbiCandidate)
            .GetMethod("CreateDirectory2W", BindingFlags.NonPublic |
                BindingFlags.Static);
        if (method == null) return 1;
        var import = (DllImportAttribute)Attribute.GetCustomAttribute(
            method, typeof(DllImportAttribute));
        if (import == null) return 1;
        Console.WriteLine(import.Value + ":" + import.EntryPoint + ":" +
            import.CharSet + ":" + import.ExactSpelling + ":" +
            import.CallingConvention + ":" + import.SetLastError);
        Console.WriteLine(method.ReturnType.FullName);
        foreach (ParameterInfo parameter in method.GetParameters())
            Console.WriteLine(parameter.ParameterType.FullName);
        return 0;
    }
}
