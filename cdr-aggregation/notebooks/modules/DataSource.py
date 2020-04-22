# Databricks notebook source
import os
if os.environ['HOME'] != '/root':
    from modules.import_packages import *
    from modules.setup_spark import *

from pyspark.sql.functions import to_timestamp
from pyspark.sql.types import *

from random import sample, seed

import datetime as dt
import pyspark.sql.functions as F

class DataSource:

  # constructor
  def __init__(self,config_input):

    #Get input config and set default values as needed
    self.setup_config(config_input)

    # Country code and company and path
    self.ccc_path = self.country_code+"/"+self.telecom_alias

    #Top folder path in datalake
    self.newdata_path     = self.base_path+"/new/"+self.ccc_path
    self.standardize_path = self.base_path+"/standardized/"+self.ccc_path
    self.results_path     = self.base_path+"/results/"+self.ccc_path
    self.tempfldr_path    = self.base_path+"/tempfiles/"+self.ccc_path

    #Support data folder paths
    self.support_data_cc = self.base_path+"/support-data/"+self.country_code
    self.support_data = self.base_path+"/support-data/"+self.ccc_path
    self.geofiles_path = self.support_data +"/geofiles"

    #filenames
    self.parquetfile = self.filestub + ".parquet"
    self.parquetfile_path = self.standardize_path +"/"+ self.parquetfile

  ######################################
  # Setup Methods

  def setup_config(self,input_config):

    #Test that the input options are a dict
    if not isinstance(input_config,dict):
      raise Exception("Input option config_input is not of type dictionary")

    #Config values : [<type>, <default value>]. If default value is None then value must be specified by user
    keys_types_defaults = {
      "base_path":[str,None],
      "country_code":[str,None],
      "telecom_alias":[str,None],
      "schema":[StructType,None],
      "filestub":[str,None],
      "data_paths":[list,["*csv.gz","*csv"]],
      "geofiles":[dict,{}],
      "load_seperator":[str,","],
      "load_header":[str,"false"],
      "load_mode":[str,"PERMISSIVE"],
      "load_datemask":[str,"dd/MM/yyyy HH:mm:ss"]
    }

    #Loop over input_confif dict to test specified values
    for config_key in input_config:

      #test that the key in cofig_output is a valid key
      if config_key not in keys_types_defaults:
        raise Exception('Key input_config["'+config_key+'"] is not an allowed key. Allowed keys are: ', keys_types_defaults.keys())

      #test that values that are of correct type
      if not isinstance(input_config[config_key],keys_types_defaults[config_key][0]):
        raise Exception('Input input_config["'+config_key+'"] is not of type '+str(keys_types_defaults[config_key][0]))

    #Loop over all config values. Use specfied values, raise error if
    #required is missing, and use default if non-required is mising
    for config_key in keys_types_defaults:

        #If value is in input_config, then use it
        if config_key in input_config:
          setattr(self, config_key, input_config[config_key])

        #If it is missing, test if it was required
        elif keys_types_defaults[config_key][1] == None:
          raise Exception('Key input_config["'+config_key+'"] is required but missing')

        #Otgherwise use default value
        else:
          setattr(self, config_key, keys_types_defaults[config_key][1])

  #Add more paths for data files in the country company folder
  def show_config(self):
    print()
    print("Basepath:", self.base_path)
    print("Country and company path:", self.ccc_path)
    print("Paths for datafiles:", self.data_paths)
    print("Geofiles:", self.geofiles)
    print("Load options:", {"seperator":self.load_seperator,"header":self.load_header,"mode":self.load_mode,"datemask":self.load_datemask})
    print("Load schema:", self.schema)
    print("Filenames:",{"parquetfile":self.parquetfile})
    print()

 ######################################
  # ETL methods

  #Load one or multiple csvs into a data frame
  def standardize_csv_files(self,show=False):

    #Prepare paths
    newfolder_data_paths = []
    for data_path in self.data_paths:
      newfolder_data_paths.append(self.newdata_path+"/"+data_path)

    #Load csv file or files using load option and schema
    raw_df = spark.read\
      .option("seperator", self.load_seperator)\
      .option("header", self.load_header)\
      .option("mode", self.load_mode)\
      .csv(newfolder_data_paths, schema=self.schema)

    #convert call_datetime string to call_datetime timestamp
    raw_df = raw_df.withColumn("call_datetime", to_timestamp("call_datetime",self.load_datemask))

    #get call_date from call_datetime
    raw_df = raw_df.withColumn('call_date', raw_df.call_datetime.cast('date'))

    #Set raw data frame to object and return it
    self.raw_df = raw_df

    if show: self.raw_df.show(10)
    return self.raw_df

  #Load one or multiple csvs into a data frame
  def save_as_parquet(self,mode="overwrite"):

    #Create the full name
    full_filename = self.standardize_path+"/"+self.parquetfile

    #Write to parquet
    self.raw_df.write.mode(mode).format("parquet").save(full_filename)

    #Load the parquet infor parquet_df
    self.load_standardized_parquet_file()

    #return file name (for display only)
    return full_filename

  #read the parquet file
  def load_standardized_parquet_file(self):
    self.parquet_df = spark.read.format("parquet").load(self.standardize_path+"/"+self.parquetfile)

######################################
 # Create sample

  #Create a sample and save to parquet
  def sample_and_save(self, filestub = 'sample' , number_of_ids = 10000, seed_to_use = 510):

    #sample a df and save to self.sample_df
    self.sample(number_of_ids,seed_to_use)

    #write sample file to parquet file and then load that sample into self.sample_df
    self.sample_df.write.mode('overwrite').parquet(self.standardize_path +"/"+ filestub)
    self.sample_df = spark.read.format("parquet").load(self.standardize_path +"/"+ filestub)
    return self.sample_df

  #Sample dataframe based on all records for sample of unique ids
  def sample(self,number_of_ids = 10000, seed_to_use = 510, since_date = dt.datetime(2020,2,2) ):
    #Get a list of all unique ids since since_date
    self.unique_ids = [i.msisdn for i in self.parquet_df.where(F.col('call_datetime') < since_date).select('msisdn').distinct().collect()]

    #Set seed and sample some ids from list of unique ids
    seed(seed_to_use)
    self.sample_ids = sample(self.unique_ids, number_of_ids)

    #Filter the full dataframe to only include the sampled IDs
    self.sample_df = self.parquet_df.filter(self.parquet_df.msisdn.isin(self.sample_ids))
    print('Successfully sampled all transactions for {} IDs'.format(number_of_ids))

  #Load a parquet sample
  def load_sample(self,  filestub = 'sample'):
    #Load sample file and return it
    self.sample_df = spark.read.format("parquet").load(self.standardize_path +"/"+ filestub)
    return self.sample_df

  def load_geo_csvs(self):
    for file in self.geofiles.keys():
        df = spark.read.format("csv")\
           .option("header", "true")\
           .option("delimiter", ",")\
           .option("inferSchema", "true")\
           .option("mode", "DROPMALFORMED")\
           .load(os.path.join(self.geofiles_path, self.geofiles[file]))
        setattr(self, file, df)
        setattr(self, file + '_pd', df.toPandas())
