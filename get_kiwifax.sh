#!/bin/sh

# 初始化变量
ServerIP=""
ServerPort="-p 8073"
ServerPassword=""
Frequency=""
Force=""
Callsign=""
custom_option=""
Debug=""
Once=""

#cd /Script/kiwiclient
BasePATH=$(pwd)
FaxPath="${BasePATH}/Fax"
LogPath="/Logs"

# 使用getopts解析参数
while getopts "s:p:P:f:C:FDoc:" opt; do
  case $opt in
    s)
      ServerIP="-s $OPTARG"
      ;;
	p)
	  ServerPort="-p $OPTARG"
	  ;;
	P)
	  ServerPassword="--pw=$OPTARG"
	  ;;
    f)
      Frequency="-f $OPTARG"
      ;;
    F)
      Force="--force-start"
      ;;
	D)
	  Debug="--debug"
	  ;;
	o)
	  Once="--once --max-height=3600"
	  ;;
	C)
	  Callsign="--station=$OPTARG"
	  ;;
    c)
      custom_option="$OPTARG"
      ;;
    \?)
      echo "无效的选项: -$OPTARG" >&2
      exit 1
      ;;
  esac
done

# 输出解析后的参数值
#echo "IP 地址: $ServerIP"
#echo "端口: $ServerPort"
#echo "频率: $Frequency"
#echo "标志 F: $Force"
#echo "自定义选项: $custom_option"

if [[ -z "$ServerIP" || -z "$Frequency" ]]; then
	echo "get_kiwifax.sh -s ServerIP [ -p ServerPort ] -f freq(kHz) [-P KiwiPassword] [-C CALLSIGN] [-F(force decode)] [-D(debug)] [-o(OnePageOnly)] [--path PNG_File_PATH] [-c OTHER OPTIONS]"
else

	DATE_TIME=$(date -u "+%Y%m%dT%H%MZ")
	echo -e "http://${ServerIP:3}:${ServerPort:3}/?ext=fax,${Frequency:3}&u=swler&no_geoloc&m" | mail -s "kiwifax ${Callsign:10} start to recveive" test@test.com
	if [[ "$Once" != "" ]]; then
		Command="timeout -s KILL 1780"
	else
		Command=""
	fi
	Command="${Command}"" /usr/bin/python3 -u ${BasePATH}/kiwifax.py ${ServerIP} ${Frequency} ${ServerPort} ${ServerPassword} $Callsign $Force $Debug $Once $custom_option --path ${FaxPath} &"
	# 输出构建的命令
	echo "构建的命令: $Command"
	# 执行命令（如果需要）
	eval "$Command"
	#/usr/bin/python3 -u $BasePATH/kiwifax.py -s 192.168.103.232 --pw=mkmz -f $FREQ_KHZ --force-start --once --debug --iq-stream --station=$Callsign --max-height=3600 --tlimit=1780 $OTHER_OPTIONS &
	#LOG=$(ls -lt log*${FREQ//./}*.log 2>/dev/null | awk '{print $9}' | head -1)
	#echo LOG file $LOG
	#if [ "$LOG" != "" ]; then
	#	tail -f $LOG | while IFS= read -r line
	#	do
			# 检查日志行是否包含 "Switching to: idle"
	#		PID_TO_KILL=$(ps aux | grep python3 | grep kiwifax | grep $FREQ | grep -v timeout | awk '{print $1}')
	#		if [ "$PID_TO_KILL" == "" ]; then
	#			break
	#		fi
	#		if echo "$line" | grep -q "Switching to: idle"; then
				# 如果找到 "Idle"，则杀死指定PID的进程
	#			kill -9 $PID_TO_KILL
	#			break  # 可选：如果只需要处理一次匹配，则跳出循环
	#		fi
	#	done
	#else
	#	echo LOG file $FREQ not found
	#fi
	wait
	sleep 5
	FREQ_HZ=$(echo "scale=0; ${Frequency:3} * 1000 / 1" | bc )
	PIC="${FaxPath}/${DATE_TIME}_${FREQ_HZ}_${Callsign:10}.png"
	if [ -f $PIC ]; then
		/usr/bin/python3 -u $BasePATH/img_process.py $PIC
		echo -e "http://${ServerIP:3}:${ServerPort:3}/?ext=fax,${Frequency:3}&u=swler&no_geoloc&m" | mailx -s "kiwifax ${Callsign:10} received" -A $PIC test@test.com
		#rm -f $PIC
	else
		echo $pic Not Found
	fi
fi
