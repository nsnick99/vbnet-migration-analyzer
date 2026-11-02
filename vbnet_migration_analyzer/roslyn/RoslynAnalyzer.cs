using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.Serialization;
using System.Runtime.Serialization.Json;
using System.Text;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.VisualBasic;

namespace VbNetMigrationAnalyzer.Roslyn
{
    [DataContract] public class DiagnosticInfo { [DataMember(Name="id")] public string Id; [DataMember(Name="severity")] public string Severity; [DataMember(Name="message")] public string Message; [DataMember(Name="path")] public string Path; [DataMember(Name="line")] public int Line; [DataMember(Name="column")] public int Column; }
    [DataContract] public class TypeInfo { [DataMember(Name="name")] public string Name; [DataMember(Name="kind")] public string Kind; [DataMember(Name="qualifiedName")] public string QualifiedName; [DataMember(Name="baseType")] public string BaseType; [DataMember(Name="interfaces")] public List<string> Interfaces = new List<string>(); [DataMember(Name="memberCount")] public int MemberCount; }
    [DataContract] public class FileInfo { [DataMember(Name="path")] public string Path; [DataMember(Name="parseErrors")] public int ParseErrors; [DataMember(Name="semanticErrors")] public int SemanticErrors; [DataMember(Name="types")] public List<TypeInfo> Types = new List<TypeInfo>(); [DataMember(Name="resolvedImports")] public List<string> ResolvedImports = new List<string>(); [DataMember(Name="calledSymbols")] public List<string> CalledSymbols = new List<string>(); }
    [DataContract] public class AnalysisOutput { [DataMember(Name="available")] public bool Available; [DataMember(Name="tool")] public string Tool; [DataMember(Name="version")] public string Version; [DataMember(Name="project")] public string Project; [DataMember(Name="syntaxDiagnostics")] public List<DiagnosticInfo> SyntaxDiagnostics = new List<DiagnosticInfo>(); [DataMember(Name="semanticDiagnostics")] public List<DiagnosticInfo> SemanticDiagnostics = new List<DiagnosticInfo>(); [DataMember(Name="files")] public List<FileInfo> Files = new List<FileInfo>(); [DataMember(Name="dependencies")] public List<object> Dependencies = new List<object>(); [DataMember(Name="apiUsage")] public List<object> ApiUsage = new List<object>(); [DataMember(Name="nativeDependencies")] public List<object> NativeDependencies = new List<object>(); [DataMember(Name="callGraph")] public List<object> CallGraph = new List<object>(); }

    internal static class Program
    {
        static string Decode(string value) => Encoding.UTF8.GetString(Convert.FromBase64String(value));
        static List<string> Sources(string manifest) => File.ReadAllLines(manifest).Where(x => x.StartsWith("SOURCE_B64\t")).Select(x => Decode(x.Substring("SOURCE_B64\t".Length))).ToList();
        static string Project(string manifest) { var x = File.ReadAllLines(manifest).FirstOrDefault(v => v.StartsWith("PROJECT_B64\t")); return x == null ? "VB.NET Project" : Decode(x.Substring("PROJECT_B64\t".Length)); }
        static string Read(string path) { var raw = File.ReadAllBytes(path); try { return Encoding.UTF8.GetString(raw); } catch { return Encoding.Default.GetString(raw); } }
        static void AddDiag(List<DiagnosticInfo> list, Diagnostic d) { var s=d.Location.GetLineSpan(); list.Add(new DiagnosticInfo { Id=d.Id, Severity=d.Severity.ToString().ToUpperInvariant(), Message=d.GetMessage(), Path=s.Path, Line=s.StartLinePosition.Line+1, Column=s.StartLinePosition.Character+1 }); }
        static void Main(string[] args)
        {
            var output = new AnalysisOutput { Available=true, Tool="Microsoft.CodeAnalysis.VisualBasic", Version=typeof(VisualBasicSyntaxTree).Assembly.GetName().Version?.ToString() ?? "unknown", Project=args.Length > 0 ? Project(args[0]) : "VB.NET Project" };
            try {
                var trees = new List<SyntaxTree>();
                foreach (var path in Sources(args[0])) {
                    var text=Read(path); var tree=VisualBasicSyntaxTree.ParseText(text, VisualBasicParseOptions.Default, path, Encoding.UTF8); trees.Add(tree);
                    var fi=new FileInfo { Path=path, ParseErrors=tree.GetDiagnostics().Count(d=>d.Severity==DiagnosticSeverity.Error) };
                    foreach (var node in tree.GetRoot().DescendantNodes()) {
                        var kind=node.Kind().ToString();
                        if (kind.Contains("Class") || kind.Contains("Structure") || kind.Contains("Module") || kind.Contains("Interface") || kind.Contains("Enum")) fi.Types.Add(new TypeInfo { Name=node.ToString().Split(new[]{' ','\r','\n','\t'},StringSplitOptions.RemoveEmptyEntries).Skip(1).FirstOrDefault() ?? "unknown", Kind=kind, QualifiedName=node.ToString().Split(new[]{'\r','\n'},StringSplitOptions.RemoveEmptyEntries).FirstOrDefault() ?? "" });
                    }
                    output.Files.Add(fi);
                    foreach (var d in tree.GetDiagnostics().Where(d=>d.Severity==DiagnosticSeverity.Error || d.Severity==DiagnosticSeverity.Warning).Take(100)) AddDiag(output.SyntaxDiagnostics,d);
                }
                var compilation=VisualBasicCompilation.Create(output.Project, trees, new MetadataReference[0], new VisualBasicCompilationOptions(OutputKind.DynamicallyLinkedLibrary, optionStrict:OptionStrict.Off));
                foreach(var d in compilation.GetDiagnostics().Where(d=>d.Severity==DiagnosticSeverity.Error || d.Severity==DiagnosticSeverity.Warning).Where(d=>d.Location.IsInSource).Take(250)) AddDiag(output.SemanticDiagnostics,d);
                foreach(var f in output.Files) f.SemanticErrors=output.SemanticDiagnostics.Count(d=>string.Equals(d.Path,f.Path,StringComparison.OrdinalIgnoreCase) && d.Severity=="ERROR");
                Write(output);
            } catch(Exception ex) { output.Available=false; output.SyntaxDiagnostics.Add(new DiagnosticInfo { Id="ROS-RUNTIME", Severity="ERROR", Message=ex.ToString(), Path="", Line=1, Column=1 }); Write(output); Environment.ExitCode=1; }
        }
        static void Write(AnalysisOutput output) { var serializer=new DataContractJsonSerializer(typeof(AnalysisOutput)); using(var ms=new MemoryStream()){ serializer.WriteObject(ms,output); Console.OutputEncoding=Encoding.UTF8; Console.WriteLine(Encoding.UTF8.GetString(ms.ToArray())); } }
    }
}
