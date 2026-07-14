// Joern CPG -> Etki normalize 'kod indeks' JSON şeması.
// Kullanım: joern --script export_cpg.sc --param cpgFile=... --param outFile=... --param root=...
// Her .py dosyası için: loc, functions, control_structures, imports (üst-seviye modül adı).

@main def exec(cpgFile: String, outFile: String, root: String) = {
  importCpg(cpgFile)

  def jstr(s: String): String =
    "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\""
  def jarr(xs: Seq[String]): String = "[" + xs.map(jstr).mkString(",") + "]"

  val realFiles = cpg.file.name.l.filter(n => n != "<empty>" && n.endsWith(".py"))

  val fileObjs = realFiles.map { f =>
    val methods = cpg.method.filter(_.filename == f).l
    val moduleEnd = methods.filter(_.name == "<module>").flatMap(_.lineNumberEnd).headOption.getOrElse(0)
    val maxEnd = methods.flatMap(_.lineNumberEnd).maxOption.getOrElse(0)
    val loc = math.max(moduleEnd, maxEnd)
    val funcs = methods.map(_.name).filter(n => !n.startsWith("<")).distinct.sorted
    val ctrl = cpg.controlStructure.filter(_.file.name.headOption.contains(f)).size
    val imps = cpg.imports
      .filter(_.call.file.name.headOption.contains(f))
      .flatMap(_.importedEntity)
      .map(_.split("\\.").head)
      .distinct
      .sorted
    s"""{"path":${jstr(f)},"loc":$loc,"functions":${jarr(funcs)},"control_structures":$ctrl,"imports":${jarr(imps)}}"""
  }

  val json = s"""{"root":${jstr(root)},"producer":"joern","files":[${fileObjs.mkString(",")}]}"""
  java.nio.file.Files.write(java.nio.file.Paths.get(outFile), json.getBytes("UTF-8"))
  println(s"WROTE ${fileObjs.size} dosya -> $outFile")
}
