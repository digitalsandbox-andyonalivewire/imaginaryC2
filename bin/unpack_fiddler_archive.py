__author__ = "Felix Weyne, 2017"

#This script's purpose is to examine and process Fiddler Session Archives (.saz file), generated by the Telerik Fiddler Web Debugger tool.
#This script 'converts' a session capture into request definitions which can be parsed by imaginary C2.
#Please note that the SAZ file needs to contain non-encoded captures. (Fiddler -> Rules -> Remove All Encodings).

#Via this script, the user can:
#	A) Generate an overview of HTTP request URLs with the corresponding stream numbers (as captured by the Fiddler archive).
#	B) Export a stream. Exporting a stream will result in:
#		-The associated HTTP response body written to a file (filename = SHA1 hash of response body)
#		-The HTTP request domain written to the redirection configuration file
#		-The HTTP request URL path written to the request configuration file

import random
import os
import sys
import re
import zipfile
import tempfile
import shutil
import glob
import urlparse
import urllib
import datetime
import hashlib
import json

archive_file_path = sys.argv[1]
fiddler_raw_dir = ""

redirected_domains = []
captured_URLs = []

default_config = "{ \"default\":{ \"source\":\"default.txt\", \"sourcetype\":\"data\"},\"requests\":[ ]}"
requests_config = json.loads(default_config)

#unpack Fiddler archive
if os.path.isfile(archive_file_path):
	try:
		temp_dir = tempfile.mkdtemp()
		print "Unpacking in: "+temp_dir
		my_zip = zipfile.ZipFile(archive_file_path,"r")
		my_zip.extractall(temp_dir)
		my_zip.close()
		fiddler_raw_dir = "%s\\raw\\" % (temp_dir)
	except Exception as e:
		print "Failed to unpack Fiddler archive" + str(e)
else:
	print "Can not find provided Fiddler file"
	sys.exit(-1)

#enumerate unpacked client request files.
c_file_list=glob.glob(fiddler_raw_dir+"*_c.txt")
c_file_list.sort()
for request in c_file_list:
	http_request = open(request).readline().rstrip()
	request_number = request.split('\\')[-1].replace("_c.txt","")
	parts = http_request.split(" ")
	if (parts[0] == "GET" or parts[0] == "POST"):
		print request_number + ": ("+parts[0]+") "+parts[1]


print "\r\n    Enter the number of the stream you want to export."
print "\r\n    Enter 'X' to stop the input"
print "\r\n    Enter 'I' to get an overview of exported resources"

stop_input = False

#create output folder on Desktop
now = datetime.datetime.now()
output_folder = os.path.join(os.environ["HOMEPATH"], "Desktop")+'\\fiddler_extract_'+now.strftime("%H_%M_%S") +'\\'
data_folder = output_folder + "server_data\\"
os.makedirs(output_folder)
os.makedirs(data_folder)
with open(data_folder+"default.txt", "a+") as file:
	file.write("Default server response! Hi!")

#Export stream functionality
exported_streams = {}	
while (stop_input == False):
	#user 'interface'
	my_input = raw_input("\r\n    Export stream:  ")
	if my_input.lower() == 'x':
		print "Stopping output"
		stop_input = True
	elif my_input.lower() == 'i':
		print ""
		for exported_stream in exported_streams:
			exported_stream_overview = ""
			for stream_property in exported_streams[exported_stream]:
				if exported_streams[exported_stream][stream_property] == True:
					exported_stream_overview = exported_stream_overview + " "+stream_property + "[X]"
			print "      *Stream "+exported_stream+": "+exported_stream_overview
	elif re.match("\d", my_input) is None:
		print "      *Your input was not a number, try again"
	elif my_input in exported_streams:
		print "      *Stream has already been exported"
	#extract HTTP response body, domain, URL path
	else:
		try:
			print "      *Exporting " +my_input
			http_request = open(c_file_list[int(my_input)-1]).readline().rstrip().split(" ")[1]
			http_request_domain = urlparse.urlparse(urllib.unquote(http_request))[1]
			if http_request_domain.find(":") != -1:
				http_request_domain, port = http_request_domain.split(':')
			http_request_path = urlparse.urlparse(urllib.unquote(http_request))[2][1:]
			print "        *domain: "+http_request_domain
			print "        *path: "+http_request_path

			http_response_file = fiddler_raw_dir + my_input + "_s.txt"

			with open(http_response_file, mode='rb') as file: 
				response_contents = file.read()
				http_response_body_offset = response_contents.find('\r\n\r\n')
				if http_response_body_offset >= 0:
					stream_properties = {"file":False, "domain":False, "path":False}
					http_headers = response_contents[:http_response_body_offset]
					http_response = response_contents[http_response_body_offset+4:]
					hash_object = hashlib.sha1(http_response)
					http_response_hex = hash_object.hexdigest()
					http_response_exported_file = data_folder + http_response_hex

					if http_request_path not in captured_URLs:
						if len(http_request_path) > 0: 
							requests_config["requests"].append({"url":http_request_path, "urltype":"fixed", "source":http_response_hex, "sourcetype":"data"})
							captured_URLs.append(http_request_path)
							with open(output_folder+"requests_config.txt", "w") as file:
								file.write(json.dumps(requests_config, indent=2))
							print "        Adding path to JSON request_config"
							stream_properties["path"] = True
						else:
							print "        <>No path found. Use the default response instead."
							continue
					else:
						print "        <>Path already in JSON request_config"

				#Double-check that encodings have been disabled
				if "Transfer-Encoding"  in http_headers:
					encoding_type = re.findall("Transfer-Encoding: ([^\r]{3,20})", http_headers)[0]
					print "        Info: seems like HTTP response is encoded with: "+encoding_type+" (transfer-encoding)"
				if "Content-Encoding" in http_headers:
					encoding_type = re.findall("Content-Encoding: ([^\r]{3,20})", http_headers)[0]
					print "        Info: seems like HTTP response is encoded with: "+encoding_type+" (content-encoding)"

					if os.path.isfile(http_response_exported_file):
						print "        <>HTTP response already written to: "+http_response_hex
					else:
						print "        Writing HTTP response to: "+http_response_hex
						with  open(http_response_exported_file, "wb") as file:
							file.write(http_response)
						stream_properties["file"] = True
					if http_request_domain not in redirected_domains:
						print "        Exporting to redirect_config: "+http_request_domain
						with open(output_folder+"redirect_config.txt", "ab") as file:
							file.write(http_request_domain+" #"+http_request_domain+"/"+http_request_path+"\r\n")
						redirected_domains.append(http_request_domain)
						stream_properties["domain"] = True
					else:
						print "        <>Domain already in redirected domains: "+http_request_domain
					exported_streams[my_input] = stream_properties
				else:
					print "Couldn't split HTTP response"
					sys.exit(-1)
		except Exception as e:
			print "      !!! Error: "+str(e)