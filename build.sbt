import sbtassembly.Plugin.AssemblyKeys._
import sbtassembly.Plugin._
import sbtassembly.Plugin.MergeStrategy

name := "Thunder"

version := "1.0"

scalaVersion := "2.9.3"

ivyXML := <dependency org="org.eclipse.jetty.orbit" name="javax.servlet" rev= "2.5.0.v201103041518"><artifact name="javax.servlet" type="orbit" ext="jar"/></dependency>

libraryDependencies += "org.apache.spark" %% "spark-core" % "0.8.0-incubating"

libraryDependencies += "org.apache.spark" %% "spark-streaming" % "0.8.0-incubating" % "provided"

libraryDependencies += "io.spray" %%  "spray-json" % "1.2.5"

resolvers += "spray" at "http://repo.spray.io/"

resolvers ++= Seq(
  "Akka Repository" at "http://repo.akka.io/releases/",
  "Spray Repository" at "http://repo.spray.cc/")

assemblySettings

  mergeStrategy in assembly <<= (mergeStrategy in assembly) { (old) =>
  {
    case "javax/servlet/SingleThreadModel.class" => MergeStrategy.first
    case x => old(x)
  }
  }





