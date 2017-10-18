import sublime
import sublime_plugin
import json
import re
import os

modelMap = {}

#constants start
sqlToJavaDataTypeMap = {
	'int': 'int',
	'smallint': 'int',
	'smallint(1)': 'int',
	'int(length==1)': 'boolean',
	'int(1<length<10)': 'int',
	'int(length>9)': 'long',
	'bigint' : 'long',
	'bigint(1)' : 'long',
	'varchar' : 'String',
	'varchar(length==1)': 'boolean',
	'varchar(length>1)' : 'String',
	'datetime' : 'Date'
}
#constants end


#common utils start
def processFunction(command):
	return {
		'POJO': getPojoString,
		'MY_BATIS': getMybatisString,
		'SERVICE': getServiceString,
		'SERVICE_IMPL': getServiceImplString,
		'CONTROLLER': getControllerString,
		'DAO': getDaoString,
		'HTML': getHtmlString,
		'DEFINITION': getDefinition,
		'META_DATA': getMetaData
	}[command]

def titleCase(snakeCaseStr):
	components = snakeCaseStr.split('_')
	return (' '.join(x.title() for x in components)).strip()

def pascalCase(snakeCaseStr):
	components = snakeCaseStr.split('_')
	return (''.join(x.title() for x in components)).strip()

def camelCase(snakeCaseStr):
	components = snakeCaseStr.split('_')
	return (components[0] + "".join(x.title() for x in components[1:])).strip()

def snakeCase(camelCaseStr):
	s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', camelCaseStr)
	return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
#common utils end

#RWS4 specific utils start
def javaDataType(sqlType):
	if not sqlType.find('(') >= 0:
		if not sqlToJavaDataTypeMap[sqlType]:
			return 'String'
		return sqlToJavaDataTypeMap[sqlType]
	try:
		length = int(sqlType.partition('(')[-1].rpartition(')')[0])
		keyword = sqlType[:sqlType.index('(')-1]
		for key in sqlToJavaDataTypeMap.keys():
			if key.find('(') > 0 and key.strip().find(keyword) == 0 and eval(key.partition('(')[-1].rpartition(')')[0]):
				return sqlToJavaDataTypeMap[key]
		return 'String'
	except:
		return 'String'
	

def javaMethodName(tableName, indexColumns, modifier):
	output = ''
	output += modifier + pascalCase(tableName)
	for columnName in indexColumns:
		idx = indexColumns.index(columnName)
		if idx == 0:
			output += 'From'
		if idx == len(indexColumns)-1 and len(indexColumns) > 1:
			output += 'And'
		output += pascalCase(columnName)
	return output

#RWS4 specific utils end

#consumers start
def loadModelMapFromFile():
	sublime.active_window().status_message('Loading cache from file')
	try:
		json_file = open('D:/model.json', 'r')
	except IOError:
		json_file = open('D:/model.json', 'w')
		return
	with open('D:/model.json') as json_file:
		global modelMap
		if os.path.getsize(os.path.realpath(json_file.name)) > 0 :
			modelMap = json.load(json_file)
		else:
			modelMap = json.loads('{}')

loadModelMapFromFile()

def consumeTable(tableString):
	global modelMap
	model = {'columns' : {}, 'primaryIndex' : [], 'uniqueIndexes' : [], 'otherIndexes' : [], 'definition':''}
	model['definition'] = tableString
	tableString = tableString.lower()
	tableString = tableString[tableString.index('create table')+12:].lower().strip(' ')
	tableName = tableString[:tableString.index('(')].strip()
	columnsString = tableString.partition('(')[-1].rpartition(')')[0].lower()
	constraintsString = ''
	if re.search(r"\b" + re.escape("constraint") + r"\b", columnsString.lower()):
		constraintIndex = re.search(r"\b" + re.escape("constraint") + r"\b", columnsString.lower()).start()
		constraintsString = columnsString[constraintIndex:].lower()
		columnsString = columnsString[:constraintIndex].lower()
	#loop over columns as easy as easy
	seqNo = 0
	for columnString in columnsString.split(',\n'):
		# for columnAttr in columnString.split(' '):
		columnAttrs = columnString.strip('\n ').strip().split()
		if len(columnAttrs) <= 0:
			continue
		columnName = columnAttrs[0]
		if len(columnAttrs) >= 2:
			model['columns'][columnName] = {'type' : columnAttrs[1]}
			model['columns'][columnName]['seqNo'] = seqNo
			seqNo += 1
			if columnString.find('not null') > 0:
				model['columns'][columnName]['req'] = True
	#handling constraints
	if constraintsString:
		for constraintString in constraintsString.split("constraint"):
			if  constraintString and constraintString.strip():
				constraintString = constraintString.strip()
				constraintString = constraintString[constraintString.index(' ')+1:].strip()
				keyType = constraintString[:constraintString.index(' ')+1].strip()
				constraintString = constraintString[constraintString.index(' ')+1:].strip()
				constraintString = constraintString[constraintString.index('('):].strip()
				columns = constraintString.partition('(')[-1].rpartition(')')[0].replace(' ','').split(',')
				if keyType.lower()=='primary':
					model['primaryIndex'] = columns
				elif keyType.lower()=='unique':
					model['uniqueIndexes'].append(columns)
	modelMap[tableName.lower()] = model

def consumeIndex(indexString, indexType):
	global modelMap
	indexString = indexString[indexString.index(' on ')+4:].lower()
	tableName = indexString[:indexString.index('(')].strip()
	columns = indexString.partition('(')[-1].rpartition(')')[0].replace(' ','').split(',')
	model = modelMap[tableName]
	if indexType == 'primary':
		model['primaryIndex'] = columns
	elif indexType == 'unique':
		model['uniqueIndexes'].append(columns)
	elif indexType == 'index':
		model['otherIndexes'].append(columns)
#consumers end

#api start
def getPojoString(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	output += 'public class ' + pascalCase(tableName) + ' {\n'
	for columnName in sorted(model['columns'], key=lambda x: (model['columns'][x]['seqNo'])):
		columnDetails = model['columns'][columnName]
		output += '\tprivate ' + javaDataType(columnDetails['type']) + ' ' + camelCase(columnName) + ';\n'
	output += '}'
	return output


def getMybatisString(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	# select primaryIndex
	primaryIndex = model['primaryIndex']
	output += '<select id="' + javaMethodName(tableName, '', 'get') + '" returnType="' + pascalCase(tableName) + '">\n'
	output += '\tselect' + '\n'
	output += '\t\t*' + '\n'
	output += '\tfrom' + '\n'
	output += '\t\t'+ tableName + '\n'
	output += '\twhere' + '\n'
	for columnName in primaryIndex:
		index = primaryIndex.index(columnName)
		output += '\t\t'
		if index != 0:
			output += 'and '
		output += columnName + ' = #{' + camelCase(columnName) + '}' + '\n'
	output += '</select>' + '\n\n'

	# select uniqueIndexes
	for uniqueIndex in model['uniqueIndexes']:
		output += '<select id="' + javaMethodName(tableName, uniqueIndex, 'get') + '" returnType="' + pascalCase(tableName) + '">\n'
		output += '\tselect' + '\n'
		output += '\t\t*' + '\n'
		output += '\tfrom' + '\n'
		output += '\t\t'+ tableName + '\n'
		output += '\twhere' + '\n'
		for columnName in uniqueIndex:
			index = uniqueIndex.index(columnName)
			output += '\t\t'
			if index != 0:
				output += 'and '
			output += columnName + ' = #{' + camelCase(columnName) + '}' + '\n'
		output += '</select>' + '\n\n'

	# insert
	output += '<insert id="' + javaMethodName(tableName, '', 'add') + '" parameterType="' + pascalCase(tableName) + '">\n'
	output += '\tinsert into ' + snakeCase(tableName) + '(\n'
	for columnName in sorted(model['columns'], key=lambda x: (model['columns'][x]['seqNo'])):
		columnDetails = model['columns'][columnName]
		output += '\t\t' + snakeCase(columnName)
		if len(model['columns'].keys()) - 1 != list(model['columns']).index(columnName):
			output += ','
		output += '\n'
	output += '\t) values (\n'
	for columnName in sorted(model['columns'], key=lambda x: (model['columns'][x]['seqNo'])):
		columnDetails = model['columns'][columnName]
		output += '\t\t#{' + camelCase(columnName) + '}'
		if len(model['columns'].keys()) - 1 != list(model['columns']).index(columnName):
			output += ','
		output += '\n'
	output += '\t)\n</insert>\n\n'

	#update
	output += '<update id="' + javaMethodName(tableName, '', 'update') + '" parameterType="' + pascalCase(tableName) + '">\n'
	output += '\tupdate'+ '\n'
	output += '\t\t\t' + snakeCase(tableName) + '\n'
	output += '\t\t<set>'+ '\n'
	for columnName in sorted(model['columns'], key=lambda x: (model['columns'][x]['seqNo'])):
		if columnName in primaryIndex:
			continue
		columnDetails = model['columns'][columnName]
		output += '\t\t\t'+ columnName + ' = #{' + camelCase(columnName) + '}'
		if len(model['columns'].keys()) - 1 != list(model['columns']).index(columnName):
			output += ','
		output += '\n'
	output += '\t\t</set>'+ '\n'
	output += '\tWHERE'+ '\n'
	for columnName in primaryIndex:
		index = primaryIndex.index(columnName)
		output += '\t\t'
		if index != 0:
			output += 'and '
		output += columnName + ' = #{' + camelCase(columnName) + '}' + '\n'
	output += '</update>' + '\n\n'

	#delete
	output += '<delete id="' + javaMethodName(tableName, '', 'delete') + '">\n'
	output += '\tdelete\n'
	output += '\t\tfrom\n'
	output += '\t' + tableName + '\n'
	output += '\t\twhere\n'
	for columnName in primaryIndex:
		index = primaryIndex.index(columnName)
		output += '\t\t'
		if index != 0:
			output += 'and '
		output += columnName + ' = #{' + camelCase(columnName) + '}' + '\n'
	output += '</delete>' + '\n\n'
	return output

def getServiceImplString(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	#select
	#primary key
	primaryIndices = model['primaryIndex']
	daoParams = ''
	output += '@Override\n'
	output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, '' , 'get') + '('
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		daoParams += camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
			daoParams += ', '
	output += ') {\n'
	output += '\treturn dao.' + javaMethodName(tableName, '' , 'get') + '(' + daoParams + ');\n}\n\n'
	#unique key
	uniqueKeys = model['uniqueIndexes']
	for uniqueKey in uniqueKeys:
		daoParams = ''
		output += '@Override\n'
		output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, uniqueKey , 'get') + '('
		for column in uniqueKey:
			output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
			daoParams += camelCase(column)
			if len(uniqueKey) - 1 != uniqueKey.index(column):
				output += ', '
				daoParams += ', '
		output += ') {\n'
		output += '\treturn dao.' + javaMethodName(tableName, uniqueKey , 'get') + '(' + daoParams + ');\n}\n\n'

	#insert
	output += '@Override\n'
	output += 'public TxnStatus ' + javaMethodName(tableName, '', 'add') + '(' + pascalCase(tableName) + ' ' + camelCase(tableName) + '){\n'
	output += '\tdao.' + javaMethodName(tableName, '', 'add') + '(' + camelCase(tableName) + ');\n'
	output += '\treturn getDefaultSuccessTxnStatus();\n}\n\n'

	#update
	#primary key
	primaryIndices = model['primaryIndex']
	daoParams = ''
	output += '@Override\n'
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'update') + '(' + pascalCase(tableName) + ' ' + camelCase(tableName) + ', '
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		daoParams += camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
			daoParams += ', '
	output += ') {\n'
	output += '\tdao.' + javaMethodName(tableName, '' , 'update') + '(' + camelCase(tableName) + ', ' + daoParams + ');\n'
	output += '\treturn getDefaultSuccessTxnStatus();\n}\n\n'

	#delete
	#primary key
	primaryIndices = model['primaryIndex']
	daoParams = ''
	output += '@Override\n'
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'delete') + '('
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		daoParams += camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
			daoParams += ', '
	output += ') {\n'
	output += '\tdao.' + javaMethodName(tableName, '' , 'delete') + '(' + daoParams + ');\n'
	output += '\treturn getDefaultSuccessTxnStatus();\n}\n\n'
	return output
	
def getServiceString(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	#select
	#primary key
	primaryIndices = model['primaryIndex']
	daoParams = ''
	output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, '' , 'get') + '('
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
	output += ');\n\n'
	#unique key
	uniqueKeys = model['uniqueIndexes']
	for uniqueKey in uniqueKeys:
		daoParams = ''
		output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, uniqueKey , 'get') + '('
		for column in uniqueKey:
			output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
			if len(uniqueKey) - 1 != uniqueKey.index(column):
				output += ', '
		output += ');\n\n'

	#insert
	#primary key
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'add') + '(' + pascalCase(tableName) + ' ' + camelCase(tableName) + ');\n\n'

	#update
	#primary key
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'update') + '(' + pascalCase(tableName) + ' ' + camelCase(tableName) + ', '
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
	output += ');\n\n'

	#delete
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'delete') + '('
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
	output += ');\n\n'
	return output

def getDaoString(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	#primary key
	primaryIndices = model['primaryIndex']
	output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, '' , 'get') + '('
	for column in primaryIndices:
		output += '@Param(value="' + camelCase(column) + '") ' + javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
	output += ');\n\n'
	#unique key
	uniqueKeys = model['uniqueIndexes']
	for uniqueKey in uniqueKeys:
		output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, uniqueKey , 'get') + '('
		for column in uniqueKey:
			output += '@Param(value="' + camelCase(column) + '") ' +javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
			if len(uniqueKey) - 1 != uniqueKey.index(column):
				output += ', '
		output += ');\n\n'

	#insert
	#primary key
	output += 'public int ' + javaMethodName(tableName, '' , 'add') + '(@Param(value="' + camelCase(tableName) + '") ' + pascalCase(tableName) + ' ' + camelCase(tableName) + ');\n\n'

	#update
	#primary key
	output += 'public int ' + javaMethodName(tableName, '' , 'update') + '(@Param(value="' + camelCase(tableName) + '") ' + pascalCase(tableName) + ' ' + camelCase(tableName) + ', '
	for column in primaryIndices:
		output += '@Param(value="' + camelCase(column) + '") ' + javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
	output += ');\n\n'

	#delete
	#primary key
	output += 'public int ' + javaMethodName(tableName, '' , 'delete') + '('
	for column in primaryIndices:
		output += '@Param(value="' + camelCase(column) + '") ' + javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
	output += ');\n\n'
	return output

def getHtmlString(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	output += '<table id = "' + camelCase(tableName) + '">\n'
	for columnName in sorted(model['columns'], key=lambda x: (model['columns'][x]['seqNo'])):
		columnDetails = model['columns'][columnName]
		output += '\t<tr>\n'
		output += '\t\t<td>'+ titleCase(columnName) + '</td>\n'
		output += '\t\t<td><input type = "text" id="' + camelCase(columnName) + '" name = "' + camelCase(columnName) + '"/></td>\n'
		output += '\t</tr>\n'
	output += '</table>\n'
	return output

def getDefinition(tableName):
	global modelMap
	model = modelMap[tableName]
	output = ''
	return output + model['definition']

def getMetaData(tableName):
	global modelMap
	model = modelMap[tableName]
	return json.dumps(model)

def getControllerString(tableName):
	global modelMap
	model = modelMap[tableName]
	controllerAnnotationsString = '@RequestMapping(value={}, method="")\n@ResponseBody\n@RfxRestShortName(value="", description="")\n@AuthorizationDefinition(control="", resource="")\n'
	output = ''
	#select
	#primary key
	primaryIndices = model['primaryIndex']
	serviceParams = ''
	output += controllerAnnotationsString
	output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, '' , 'get') + '('
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		serviceParams += camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
			serviceParams += ', '
	output += ') {\n'
	output += '\treturn service.' + javaMethodName(tableName, '' , 'get') + '(' + serviceParams + ');\n}\n\n'
	#unique key
	uniqueKeys = model['uniqueIndexes']
	for uniqueKey in uniqueKeys:
		serviceParams = ''
		output += controllerAnnotationsString
		output += 'public ' + pascalCase(tableName) + ' ' + javaMethodName(tableName, uniqueKey , 'get') + '('
		for column in uniqueKey:
			output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
			serviceParams += camelCase(column)
			if len(uniqueKey) - 1 != uniqueKey.index(column):
				output += ', '
				serviceParams += ', '
		output += ') {\n'
		output += '\treturn service.' + javaMethodName(tableName, uniqueKey , 'get') + '(' + serviceParams + ');\n}\n\n'

	#insert
	#primary key
	output += controllerAnnotationsString
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'add') + '(' + pascalCase(tableName) + ' ' + camelCase(tableName) + '){\n'
	output += '\treturn service.' + javaMethodName(tableName, '' , 'add') + '(' + camelCase(tableName) + ');\n}\n\n'

	#update
	#primary key
	output += controllerAnnotationsString
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'update') + '(' + pascalCase(tableName) + ' ' + camelCase(tableName) + ', '
	serviceParams = camelCase(tableName) + ', '
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		serviceParams += camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
			serviceParams += ', '
	output += ') {\n'
	output += '\treturn service.' + javaMethodName(tableName, '' , 'update') + '(' + serviceParams + ');\n}\n\n'

	#delete
	#primary key
	serviceParams = ''
	output += controllerAnnotationsString
	output += 'public TxnStatus ' + javaMethodName(tableName, '' , 'delete') + '('
	for column in primaryIndices:
		output += javaDataType(model['columns'][column]['type']) + ' ' + camelCase(column)
		serviceParams += camelCase(column)
		if len(primaryIndices) - 1 != primaryIndices.index(column):
			output += ', '
			serviceParams += ', '
	output += ') {\n'
	output += '\treturn service.' + javaMethodName(tableName, '' , 'delete') + '(' + serviceParams + ');\n}\n\n'
	return output
#api end

def processSelections(view, edit, command):
	view.run_command('split_selection_into_lines')
	for sel in view.sel():
		region = sel if sel else view.word(sel)
		# for subRegion in view.split_by_newlines(region):
		text = view.substr(region).strip()
		# Preserve leading and trailing whitespace
		leading = text[:len(text)-len(text.lstrip())]
		trailing = text[len(text.rstrip()):]
		resultText = leading + processFunction(command)(snakeCase(text.strip()).lower()) + trailing
		if resultText != text:
			view.replace(edit, region, resultText)

class CodeBotLoadDataCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		sublime.active_window().status_message('processing and uploading model')
		self.loadFromSelections(edit)
		with open('D:/model.json', 'w') as outfile:  
			global modelMap
			json.dump(modelMap, outfile)

	def loadFromSelections(self, edit):
		sels = self.view.sel()
		for sel in sels:
			for segment in self.view.substr(sel).split(';'):
				self.loadSegment(edit, segment.strip())

	def loadSegment(self, edit, segmentStr):
		if segmentStr.lower().find('create ')  and segmentStr.lower().find(' table ') >= 0:
			consumeTable(segmentStr)
		#indexs logic here
		elif segmentStr.lower().find('create primary ') >= 0:
			consumeIndex(segmentStr, 'primary')
		elif segmentStr.lower().find('create unique ') >= 0:
			consumeIndex(segmentStr, 'unique')
		elif segmentStr.lower().find('create index ') >= 0:
			consumeIndex(segmentStr, 'index')

class CodeBotGetDefinitionCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'DEFINITION')

class CodeBotGetMetaDataCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'META_DATA')

class CodeBotGetPojoCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'POJO')

class CodeBotGetMyBatisCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'MY_BATIS')

class CodeBotGetServiceCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'SERVICE')

class CodeBotGetServiceImplCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'SERVICE_IMPL')

class CodeBotGetControllerCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'CONTROLLER')

class CodeBotGetDaoCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'DAO')

class CodeBotGetHtmlCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		processSelections(self.view, edit, 'HTML')


# class CodeBotLoadModelMapCommand(sublime_plugin.WindowCommand):
# 	def run(self):
# 		loadModelMapFromFile()

class CodeBotFeelingLuckyCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		fileName = self.view.file_name()
		if fileName == None:#default
			processSelections(self.view, edit, 'DEFINITION')
		elif fileName.find('.java') >= 0 and fileName.find('Default') >= 0 and fileName.find('Service'):
			processSelections(self.view, edit, 'SERVICE_IMPL')
		elif fileName.find('.java') >= 0 and fileName.find('Service') >= 0:
			processSelections(self.view, edit, 'SERVICE')
		elif fileName.find('.java') >= 0 and fileName.find('DAO') >= 0:
			processSelections(self.view, edit, 'DAO')
		elif fileName.find('.java') >= 0 and fileName.find('Controller') >= 0:
			processSelections(self.view, edit, 'CONTROLLER')
		elif fileName.find('.java') >= 0:
			processSelections(self.view, edit, 'POJO')
		elif fileName.find('.xml') >= 0:
			processSelections(self.view, edit, 'MY_BATIS')
		elif fileName.find('.html') >= 0 or fileName.find('.jsp') >= 0 or fileName.find('.tmpl') >= 0 or fileName.find('.view') >= 0:
			processSelections(self.view, edit, 'HTML')

class QueryBuilderCommand(sublime_plugin.TextCommand):
	# selectedItems = []
	# suggestions = []
	# edit = null
	def run(self, edit, selectedItems=[], suggestions=[]):
		self.selectedItems = selectedItems
		self.suggestions = suggestions
		self.edit = edit
		self.processMenu()


	def on_done(self, index):
		if index == -1:
			return
		for sel in self.view.sel():
			region = sel if sel else self.view.word(sel)
			text = self.view.substr(region).strip()
			self.view.replace(self.edit, region, text + ', ' + json.dumps(self.suggestions[index]))
		self.selectedItems.insert(len(self.selectedItems), self.suggestions[index])
		self.suggestions.pop(index)
		sublime.set_timeout(self.triggerPopup, 100)

	def processMenu(self):
		global modelMap
		if len(self.selectedItems) == 0:
			self.suggestions = list(modelMap.keys())
			self.view.show_popup_menu(self.suggestions, self.on_done)
			return
		print('suggestions')
		print(self.suggestions)
		self.view.show_popup_menu(self.suggestions, self.on_done)

	def triggerPopup(self):
		self.view.run_command("query_builder", {"selectedItems": self.selectedItems, "suggestions": self.suggestions})
