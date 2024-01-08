#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import csv
import sys
import json
import time
import pickle
import logging
import traceback

from twilio.rest import Client
from logging import NOTSET, DEBUG, INFO, WARNING, ERROR, CRITICAL, FATAL

MENU_NULL = 0

MENU_MERGE = 1
MENU_LOAD = 2
MENU_SEND = 3
MENU_TEST = 4
MENU_RECOVERY = 5
MENU_SHOW_VICTIMS = 6
MENU_SETTINGS = 7
MENU_QUIT = 8

MENU_SETTINGS_SLEEP = 1
MENU_SETTINGS_COST = 2
MENU_SETTINGS_SENDER = 3
MENU_SETTINGS_VICTIM_FILE = 4
MENU_SETTINGS_USE_COLOR = 5
MENU_SETTINGS_LOGGING_LEVEL = 6
MENU_SETTINGS_LOGGING_FILE_NAME = 7
MENU_SETTINGS_RECOVERY = 8
MENU_SETTINGS_RECOVERY_FILE_NAME = 9
MENU_SETTINGS_BACK = 10

MENU_LOGGING_LEVEL_NOTSET = 1
MENU_LOGGING_LEVEL_DEBUG = 2
MENU_LOGGING_LEVEL_INFO = 3
MENU_LOGGING_LEVEL_WARN = 4
MENU_LOGGING_LEVEL_ERROR = 5
MENU_LOGGING_LEVEL_CRITICAL = 6
MENU_LOGGING_BACK = 7

class Singleton(type):
	_instances = {}
	def __call__(cls, *args, **kwargs):
		if cls not in cls._instances:
			cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
		return cls._instances[cls]

class Application(object, metaclass=Singleton):
	LOGGING_LEVEL_DICT = {
		"debug" : DEBUG,
		"info" : INFO,
		"warning" : WARNING,
		"error" : ERROR,
		"critical" : CRITICAL,
	}

	__configFileName = "{}{}".format(os.path.splitext(os.path.basename(__file__))[0], '.conf')
	__loaded = False
	recovery = True
	savedRecoveryFileName = "recovery.list"
	cost = 0.0075
	sleep = 2.0
	senderPhoneNumber = ""
	useColor = True
	loggingLevel = LOGGING_LEVEL_DICT["info"]
	loggingFileName = "sendtest.log"
	savedVictimFileName = "victims.list"
	TWILIO_ACCOUNT_SID = None
	TWILIO_AUTH_TOKEN = None
	victimList = set()
	recoveryList = set()

	def __setattr__(self, attr, value):
		if(not self.__loaded):
			self.__dict__[attr] = value
		else:
			self.__dict__[attr] = value
			self.__saveConfigToFile()

	def __saveConfigToFile(self):
		with open(self.__configFileName, 'w') as cf:
			cf.write(json.dumps(
				{
					"recovery" : self.recovery,
					"savedRecoveryFileName" : self.savedRecoveryFileName,
					"cost" : self.cost,
					"sleep" : self.sleep,
					"senderPhoneNumber" : self.senderPhoneNumber,
					"useColor" : self.useColor,
					"loggingLevel" : logging.getLevelName(self.loggingLevel).lower(),
					"loggingFileName" : self.loggingFileName,
					"savedVictimFileName" : self.savedVictimFileName,
					"TWILIO_AUTH_TOKEN" : self.TWILIO_AUTH_TOKEN,
					"TWILIO_ACCOUNT_SID" : self.TWILIO_ACCOUNT_SID
				}, 
				indent=4
				)
			)

	def loadConfigFromFile(self):
		if not os.path.exists(self.__configFileName):
			Logger().critical("Could not load configuration file '{}'. The script will automatically create one with default values.".format(self.__configFileName))
			Logger().warning("Attempt to create configuration file '{}'...".format(self.__configFileName))
			self.__saveConfigToFile()
			Logger().info("Successfully created '{}'.".format(self.__configFileName))

			sys.exit(0)
		elif not os.path.isfile(self.__configFileName):
			Logger().critical("Could not load configuration file '{}' has it is not a file.".format(self.__configFileName))
			sys.exit(0)
		else:
			with open(self.__configFileName, 'r') as cf:
				self.__dict__.update(json.loads(cf.read()))

			self.loggingLevel = self.LOGGING_LEVEL_DICT[self.loggingLevel.lower()]

			try:
				if self.TWILIO_AUTH_TOKEN is None:
					self.TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
				if self.TWILIO_ACCOUNT_SID is None:
					self.TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
			except KeyError as ke:
				Logger().critical("TWILIO_AUTH_TOKEN and/or TWILIO_ACCOUNT_SID is None in '{}' and is missing in environment variables.".format(self.__configFileName))
				sys.exit(1)

			self.__loaded = True

			Logger().info("Loaded configuration from file '{}'.".format(self.__configFileName))

class ColoredFormatter(logging.Formatter):
	COLOR_SEQ = "\033[1;{}m"
	RESET_SEQ = "\033[0m"

	COLORS = {
		'DEBUG': 6,
		'INFO': 4,
		'WARNING': 3,
		'ERROR': 1,
		'CRITICAL': 1,
		'FATAL': 1,
	}

	def __init__(self, fmt, useColor=True):
		logging.Formatter.__init__(self, fmt)
		self.__useColor = useColor

	def format(self, record):
		if self.__useColor and record.levelname in self.COLORS:
			record.msg = "{color}{msg}{reset}".format(color=self.COLOR_SEQ.format(30 + self.COLORS[record.levelname]),msg=record.msg,reset=self.RESET_SEQ)
			record.msg = "{color}{msg}{reset}".format(color=self.COLOR_SEQ.format(30 + self.COLORS[record.levelname]),msg=record.msg,reset=self.RESET_SEQ)

		return logging.Formatter.format(self, record)

	def toggleUseColor(self, useColor):
		self.__useColor = useColor
		
class Logger(object, metaclass=Singleton):
	def __init__(self):
		self.__logger = logging.getLogger(Application().loggingFileName)
		self.__logger.setLevel(DEBUG)

		self.__fh = logging.FileHandler(Application().loggingFileName)
		self.__fh.setLevel(INFO)
		self.__fh.setFormatter(logging.Formatter(fmt="%(asctime)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

		self.__colorFormatter = ColoredFormatter(fmt="%(message)s", useColor=Application().useColor)

		self.__sh = logging.StreamHandler()
		self.__sh.setLevel(Application().loggingLevel)
		self.__sh.setFormatter(self.__colorFormatter)

		self.__logger.addHandler(self.__fh)
		self.__logger.addHandler(self.__sh)
		
	def __getattr__(self, attr):
		return self.__logger.__getattribute__(attr)

	def updateStreamLevel(self):
		self.__sh.setLevel(Application().loggingLevel)

	def updateUseColor(self):
		self.__colorFormatter.toggleUseColor(Application().useColor)

class Victim(object):
	def __init__(self, firstname, lastname, email, uid, phonenumber):
		self.__firstname = firstname
		self.__lastname = lastname
		self.__email = email
		self.__uid = uid
		self.__phonenumber = phonenumber

	def __str__(self):
		return str(self.__dict__)

	def __repr__(self):
		return str(self.__dict__)

	def getFirstname(self):
		return self.__firstname

	def getLastname(self):
		return self.__lastname

	def getEmail(self):
		return self.__email

	def getUID(self):
		return self.__uid

	def getPhoneNumber(self):
		return self.__phonenumber

def merger(uidCSVPath, victimInfoCSVPath):
	Logger().info("Parsing files")

	victimSet = set()
	victimDict = dict()

	with open(uidCSVPath, 'r', newline='') as uidCSVFile:
		victimUID = csv.DictReader(uidCSVFile, delimiter=',')

		for victim in victimUID:
			victimDict[victim["Email"]] = [victim["First Name"], victim["Last Name"], victim["UID"]]

	with open(victimInfoCSVPath, 'r', newline='') as victimInfoCSVFile:
		victimInfo = csv.DictReader(victimInfoCSVFile, delimiter=',')

		for victim in victimInfo:
			email = victim["Email"]
			if email in victimDict:
				firstName = victimDict[email][0] if victimDict[email][0] != "" else victim["First Name"]
				lastName = victimDict[email][1] if victimDict[email][1] != "" else victim["Last Name"]

				uid = victimDict[email][2]
				phonenumber = victim["Phone Number"]

				if firstName == "":
					Logger().debug("Missing First name for {}".format(email))

				if lastName == "":
					Logger().debug("Missing Last name for {}".format(email))

				if uid == "":
					Logger().error("Missing UID for {}. Skipping...".format(email))
					continue

				if phonenumber == "":
					Logger().error("Missing Phone Number for {}. Skipping...".format(email))
					continue

				victimSet.add(
					Victim(
						email=email,
						firstname=firstName,
						lastname=lastName,
						uid=uid,
						phonenumber=phonenumber
					)
				)

	if(len(victimSet) > 0):
		Logger().info("{} victims has been parsed".format(len(victimSet)))
	else:
		Logger().warning("No victim was parsed")

	return victimSet

def save(filename, victims):
	with open(filename, 'w', newline='') as file:
		csvfile = csv.DictWriter(file, fieldnames=['First Name', 'Last Name', 'Email', 'UID', 'Phone Number'], delimiter=',', quoting=csv.QUOTE_MINIMAL)
		csvfile.writeheader()

		for victim in victims:
			csvfile.writerow({
				"First Name": victim.getFirstname(),
				"Last Name": victim.getLastname(),
				"Email": victim.getEmail(),
				"UID": victim.getUID(),
				"Phone Number": victim.getPhoneNumber(),
			})

	Logger().debug("Victims has been saved in '{}'".format(filename))

def load(filename):
	victimSet = set()
	with open(filename, 'r') as file:
		csvfile = csv.DictReader(file, delimiter=',')

		for victim in csvfile:
			victimSet.add(
				Victim(
					email=victim["Email"],
					firstname=victim["First Name"],
					lastname=victim["Last Name"],
					uid=victim["UID"],
					phonenumber=victim["Phone Number"]
				)
			)

	if victimSet:
		Logger().info("Successfully loaded {} victim phonenumbers".format(len(victimSet)))
	else:
		Logger().info("Failed to load victims from file.")

	return victimSet

def sendSMS(victim, body):
	result = None
		
	Logger().info("Sending SMS to {} {} at {}".format(victim.getFirstname(), victim.getLastname(), victim.getPhoneNumber()))
		
	client = Client(Application().TWILIO_ACCOUNT_SID, Application().TWILIO_AUTH_TOKEN)
	message = client.messages \
		.create(
			body=body,
			from_=Application().senderPhoneNumber,
			to=victim.getPhoneNumber()
		)
	result = message

	if result and result.status in ('sent', 'queued'):
		Logger().debug("Sent SMS to {}".format(victim.getPhoneNumber()))
	else:
		Logger().error("Failed to send SMS to {}".format(victim.getPhoneNumber()))
	
	return result

def presend(victims, messagePath, recovery=False, phishingLink="https://"):
	with open(messagePath, 'r') as f:
		message = f.read()
		f.close()
	cost = Application().cost * len(victims)
	answer = input("Start sending {} SMS for ${} (Y/[N])? ".format(len(victims), cost))
	if(answer.upper() == "Y"):
		i = 1

		if(recovery):
			save(Application().savedRecoveryFileName, Application().recoveryList)

		message = message.replace("{link}", phishingLink)

		for victim in victims:
			body = message \
				.replace("{firstname}", victim.getFirstname()) \
				.replace("{lastname}", victim.getLastname()) \
				.replace("{email}", victim.getEmail()) \
				.replace("{uid}", victim.getUID()) \
				.replace("{phonenumber}", victim.getPhoneNumber())
	
			if(sendSMS(victim, body)):
				if(recovery):
					Application().recoveryList.remove(victim)
					save(Application().savedRecoveryFileName, Application().recoveryList)
					Logger().debug("Remaining {} victims.".format(len(Application().recoveryList)))
			
				Logger().info("{}/{} sms sent".format(i, len(victims)))

				i += 1
			
			# Adding a sleep to reduce speed
			time.sleep(Application().sleep)
		
		Logger().info("Sending SMS is done")

def clearscreen():
	os.system("clear")

def header():
	print("Please make a choice from the following list.")
	print("")
	print("")

def menu():
	clearscreen()
	header()
	print("[{}] - Merge XML from Phishing Frenzy and CSV victims file from client".format(MENU_MERGE))
	print("[{}] - Load victims from file ({})".format(MENU_LOAD, Application().savedVictimFileName))
	print("[{}] - Send SMS".format(MENU_SEND))
	print("[{}] - Send a test SMS".format(MENU_TEST))
	print("[{}] - Recover from last attempt ({})".format(MENU_RECOVERY, Application().savedRecoveryFileName))
	print("[{}] - Show loaded victims ({})".format(MENU_SHOW_VICTIMS, len(Application().victimList)))
	print("[{}] - Settings".format(MENU_SETTINGS))
	print("[{}] - Quit".format(MENU_QUIT))

	try:
		answer = int(input("Enter choice number: "))
	except ValueError as ve:
		answer = MENU_NULL

	return answer

def nullMenu():
	clearscreen()
	Logger().warning("Only a valid number is accepted")
	input("Press any key to return to the menu...")

def loadMenu():
	try:
		Application().victimList = load(Application().savedVictimFileName)
		Application().recoveryList = Application().victimList.copy()
	except FileNotFoundError as fnfe:
		Logger().warning("File not found '{}', change the file name in settings.".format(Application().savedVictimFileName))
	# input("Press any key to return to the menu...")
	

def sendMenu(link):
	if Application().victimList:
		messagePath = "message.txt"
		presend(Application().victimList, messagePath, recovery=Application().recovery, phishingLink=link)
	else:
		Logger().warning("No victim loaded")
	# input("Press any key to return to the menu...")

def main(phishingLink):
	loadMenu()
	sendMenu(phishingLink)

if __name__ == '__main__':
	link = ""
	if (len(sys.argv) > 1):
		link = sys.argv[1]

	try:
		Application().loadConfigFromFile()
		main(link)
	except KeyboardInterrupt as ki:
		print("")
	except Exception as e:
		Logger().critical(traceback.format_exc())
		sys.exit(1)
	
	sys.exit(0)