# Databricks notebook source
# DBTITLE 1,Load "US Census Public Use Microdata Survery" (about 1.5 million people from California)

import urllib.request

url = "https://raw.githubusercontent.com/opendifferentialprivacy/dp-test-datasets/master/data/PUMS_california_demographics/data.csv"
urllib.request.urlretrieve(url,"/tmp/pums_large.csv")
dbutils.fs.mv("file:/tmp/pums_large.csv","dbfs:/data/pums_large.csv")

metadataUrl = "https://raw.githubusercontent.com/opendifferentialprivacy/whitenoise-samples/5e1029614dd983c34cdbdc6f78c7b9528e1125b5/data/readers/PUMS_large.yaml"
urllib.request.urlretrieve(metadataUrl,"/tmp/PUMS_large.yaml")
dbutils.fs.mv("file:/tmp/PUMS_large.yaml","dbfs:/data/PUMS_large.yaml")

# COMMAND ----------

# DBTITLE 1,Execute an aggregation query to get count by dimensions "sex, age, educ, latino, black, asian, married"
from pyspark.sql.functions import count, desc
df = spark.read.csv("dbfs:/data/pums_large.csv", header=True, inferSchema= True)
agg_df =  df.dropna().groupby(df.sex, df.age, df.educ, df.latino, df.black, df.asian, df.married).agg(count("*").alias("cnt")).sort("cnt")
agg_df.show()

# COMMAND ----------

trackingOnePerson = df.filter((df.sex == 1) & (df.age == 84) & (df.educ == 5) & (df.latino == 1) & (df.black == 0) & (df.asian == 0) & (df.married == 1))
display(trackingOnePerson)

# COMMAND ----------

# DBTITLE 1,Apply Differential Privacy on query
from pyspark.sql import SparkSession
from opendp.whitenoise.sql import SparkReader, PrivateReader
from opendp.whitenoise.metadata import CollectionMetadata
from opendp.whitenoise.sql.private_reader import PrivateReaderOptions

meta = CollectionMetadata.from_file('/dbfs/data/PUMS_large.yaml')
query = 'SELECT sex, age, educ, latino, black, asian, married, COUNT(PersonID) AS Cnt FROM PUMS_large GROUP BY sex, age, educ, latino, black, asian, married'

df = df.withColumnRenamed("_c0", "PersonID")
df.createOrReplaceTempView("PUMS_large")

opendpsc = SparkSession.builder.appName('opendpsc').getOrCreate()
reader = SparkReader(opendpsc)
reader.compare.search_path = ["PUMS"] # We need to tell the reader that all tables used in the query are avaialble under default schema named 'PUMS'

prOptions = PrivateReaderOptions(censor_dims = False, reservoir_sample=False, clamp_counts=False)
private = PrivateReader(meta, reader, 1.0, options = prOptions)
priv = private.execute_typed(query)

priv.show()

# COMMAND ----------

from pyspark.sql.types import IntegerType
from pyspark.sql.functions import udf

booltoIntUdf = udf(lambda x: int(x), IntegerType())

privNew = priv.withColumn("latino", booltoIntUdf("latino")) \
              .withColumn("black", booltoIntUdf("black")) \
              .withColumn("asian", booltoIntUdf("asian")) \
              .withColumn("married", booltoIntUdf("married"))  

# COMMAND ----------

trackingOnePerson = priv.filter((priv.sex == 1) & (priv.age == 84) & (priv.educ == 5) & (priv.latino == 1) & (priv.black == 0) & (priv.asian == 0) & (priv.married == 1))
display(trackingOnePerson)

# COMMAND ----------

# DBTITLE 1,Join exact and private result
joined_df = exact.join(priv, (exact.sex == priv.sex) & (exact.age == priv.age) & (exact.educ == priv.educ) & (exact.latino == priv.latino) & (exact.black == priv.black) & (exact.asian == priv.asian) & (exact.married == priv.married), "inner").select(exact['*'], privdf['Cnt'].alias('PrivCnt'))

# COMMAND ----------

# DBTITLE 1,Compare exact and private result
# Compare total count
display(joined_df)

# COMMAND ----------

# Compare count by "married"
display(joined_df)

# COMMAND ----------

# Compare count by "sex" and "race"
display(joined_df.sort(desc("Cnt")))

# COMMAND ----------

# Compare count equal to 1
display(joined_df.filter(joined_df.Cnt == 1))
